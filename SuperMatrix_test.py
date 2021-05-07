
import RSU
import SignalPlan
import traci
import math
import configparser

from scipy.stats import norm
from distutils.util import strtobool

#
import time
start_time = time.time()

# Config File Parser
config = configparser.ConfigParser()
config.read('Config.ini')

###### Global Parameters ######
MAX_ADJUST_RATIO = float(config['DEFAULT']['MAX_ADJUST_RATIO'])
SPEED = [int(config['DEFAULT']['SPEED'])]
Thr = float(config['DEFAULT']['PASS_PROBABILITY_Threshold'])

OUTPUT_WITH_INPUT_COLUMN = strtobool(config['OPTIONS']['OUTPUT_WITH_INPUT_COLUMN'])
OUTPUT_FILE_PATH = config['OPTIONS']['OUTPUT_FILE_PATH']
SIGNAL_PLAN_FILE_NAME = config['OPTIONS']['SIGNAL_PLAN_FILE_NAME']
ASSIGENED_PLAN_NUM = int(config['OPTIONS']['ASSIGENED_PLAN_NUM'])

RSUs = dict()
def setPhaseObject(i, inputPlan, planID, phaseOrder, offset):
    #I = RSU物件

    inputPlanLength = len(inputPlan)
    PhaseObjectList = []


    # Phase實體化，並加入PhaseObjectList
    for phase in range(0, inputPlanLength):
        PhaseObjectList.append(SignalPlan.Phase(phaseID=inputPlan[phase]['phaseID'], startTime=inputPlan[phase]['startTime'],
                                                greenSplit=inputPlan[phase]['greenSplit'],green=inputPlan[phase]['green'], yellow=inputPlan[phase]['yellow'],
                                                allRed=inputPlan[phase]['allRed'], Gmin=inputPlan[phase]['Gmin'], Gmax=inputPlan[phase]['Gmax'], pedFlash=inputPlan[phase]['pedFlash'],
                                                pedRed=inputPlan[phase]['pedRed'], IsAdjustable=inputPlan[phase]['IsAdjustable'], MAX_ADJUST_RATIO=MAX_ADJUST_RATIO))

    CYCLE = 0
    for phase in PhaseObjectList:  # 計算週期
        CYCLE = CYCLE + phase.greenSplit + phase.pedRed + phase.allRed + phase.yellow

    signalPlan = SignalPlan.SignalPlan()  # 將SignalPlan物件實體化
    signalPlan.setAllParameters(planID=planID, phaseOrder=phaseOrder, offset=offset, cycle=CYCLE, phases=PhaseObjectList)

    print("signalPlan = ", signalPlan)
    i.addPlan(plan=signalPlan)  # 新增這組Plan至RSU
    i.setOriginalPlan(plan=signalPlan)  # 將這組plan指定為原始時制計畫(originalPlan)

def initialization():

    # 初始化: 新增RSU
    rsu1 = RSU.BusRSU(ID='RSU1', location=[100, 0], VANET_detection_range=300)
    # 設定各RSU的時制
    RSUs.update({'rsu1': rsu1})
    print(RSUs['rsu1'].RSU_ID)
    print(RSUs['rsu1'].location)

    import csv
    # 開啟 CSV 檔案
    Plan = []
    PlanID = 0
    planNumber = 0

    with open(SIGNAL_PLAN_FILE_NAME, newline='') as csvfile:

        countrows = csv.DictReader(csvfile)
        totalrows = 0
        for row in countrows:
            totalrows += 1

        csvfile.seek(0)
        rows = csv.DictReader(csvfile)

        # 讀取 CSV 檔案內容
        # 以迴圈輸出每一列
        for row in rows:
            # 交控中心的時比和我的定義不同:
            # 交控中心: 時比 = 綠燈 + 黃燈 + 全紅
            # 我的: 時比 = 綠燈 + 行閃
            # greenSplit_revised 先將定義轉換

            greenSplit = int(row['Green']) + int(row['PedFlash'])
            Phase = {'startTime': 0, 'phaseID': int(row['PhaseID'])-1, 'greenSplit': greenSplit,
                     'green': int(row['Green']), 'pedFlash': int(row['PedFlash']), 'yellow': int(row['Yellow']),
                     'allRed': int(row['AllRed']), 'pedRed': int(row['PedRed']), 'Gmin': int(row['MinGreen']),
                     'Gmax': int(row['MaxGreen']), 'IsAdjustable': strtobool(row['IsAdjustable'])}

            if (int(row['PlanID'])-1 == PlanID): #檢核用
                Plan.append(Phase)
                phaseOrder = row['PhaseOrder']
                offset = row['Offset']
                if ((rows.line_num-1) == totalrows): #若已經是csv中最後一條row -> setPhaseObject
                    setPhaseObject(i=RSUs['rsu1'], inputPlan=Plan, planID=PlanID, phaseOrder=row['PhaseOrder'],
                                   offset=row['Offset'])
                    planNumber = planNumber + 1
            else:
                setPhaseObject(i=RSUs['rsu1'], inputPlan=Plan, planID=PlanID, phaseOrder=phaseOrder, offset=offset)
                Plan = [] #將Plan清空
                PlanID = int(row['PlanID'])-1 #換新的PlanID
                Plan.append(Phase)
                planNumber = planNumber + 1

    for plan in RSUs['rsu1'].plan:
        print("RSUs['rsu1'] = ", plan)

    return planNumber


planNum = initialization()  # 初始化號誌物件

# 計算路口通過機率
def calPassProb(dist, arrivalTime, phaseTimeSplit, greenTag):  # 傳入路口RSU物件

    # print("arrival time = ", arrivalTime)
    deviation = math.ceil((2 + dist / 50) / 3)  # 標準差
    upBound = round(arrivalTime + 3 * deviation)  # 抵達時間上界
    lowBound = max(0, round(arrivalTime - 3 * deviation))  # 抵達時間下界
    arrivalBound = [b for b in range(lowBound, upBound + 1)]  # 列出預計抵達時間離散化範圍
    #print("arrivalBound = ", arrivalBound)

    # 計算未來時制計畫紅燈與綠燈時間點(phaseTimeSplit)
    ### 指出紅燈區段是哪些時間點 ###
    redBound = []

    if (greenTag == 0):  # greenTag = 0 --> [(0) 綠燈  (1) 綠燈結束, (2) 綠燈開始, (3)綠燈結束,..., (n)綠燈開始 (n+1) 綠燈結束]
        # phaseSplit兩兩一組，各自產生離散化範圍
        for n in range(1, len(phaseTimeSplit)-1, 2):
            redBound.extend([time for time in range(phaseTimeSplit[n], phaseTimeSplit[n + 1] + 1)])  # 列出紅燈的時間範圍
        #print("離散化的紅燈秒數區間 = ", redBound)

    else:
        # greenTag = 1 -->  # [(0) 綠燈尚未開始(紅燈)  (1) 綠燈開始, (2) 綠燈結束, (3)綠燈開始,..., (n)綠燈結束]
        for n in range(0, len(phaseTimeSplit)-1, 2):
            redBound.extend([time for time in range(phaseTimeSplit[n], phaseTimeSplit[n + 1] + 1)])  # 列出紅燈的時間範圍
        #print("離散化的紅燈秒數區間 = ", redBound)

    ### 計算路口i的通過機率 ###
    # 計算紅燈區段和抵達時間區段之交集
    intersectResult = list(set(arrivalBound).intersection(set(redBound)))
    intersectResult.sort()  # 因為SET取交集可能使其沒有排序好
    redTimeRange = []  # 紀錄取交集後之紅燈時間長度
    redProbSet = []  # 紀錄紅燈機率

    # 交集後可能包含區間橫跨兩個時相，因此需要個別指出
    for num in range(1, len(intersectResult)):  # 比較在取交集之集合中，後一個數字是否是前一個+1
        if (intersectResult[num] == intersectResult[num - 1] + 1):
            # 若是，則表示還在原本的切割範圍，繼續加至紅燈時間長度
            redTimeRange.append(intersectResult[num - 1])
        else:
            # 若否，表示num已經是新的切割區域
            redTimeRange.append(intersectResult[num - 1])  # 先將num-1加至舊的切割區域
            # 計算舊的切割區域之(紅燈)機率
            redProb = norm.cdf(x=max(redTimeRange), loc=arrivalTime, scale=deviation) \
                      - norm.cdf(x=min(redTimeRange), loc=arrivalTime, scale=deviation)
            redProbSet.append(redProb)  # 將計算結果apped到redProbSet
            redTimeRange.clear()  # 清除紅燈計算範圍

        if (num == len(intersectResult) - 1 and len(redTimeRange) > 0):
            # 最後一部分: 若已經到intersectionResult底 且 redTimeRange還有沒被清空的部分
            redTimeRange.append(intersectResult[num])
            redProb = norm.cdf(x=max(redTimeRange), loc=arrivalTime, scale=deviation) \
                      - norm.cdf(x=min(redTimeRange), loc=arrivalTime, scale=deviation)
            redProbSet.append(redProb)

    # 通過機率 = 1 - (紅燈機率) #
    result = 1
    for prob in redProbSet:
        # 將路口通過機率寫入
        result = result - prob
    #print("通過機率 = ", result)
    return result


def Algorithm2_1(RSU, truncate_red_light_to_min, appliedPlanNum, prioritizedPhase, currentPhase, pts, greenTag, a, b, remainingTime, numOfCycleToProcess):
    # a -> non-prioritized phase / b -> prioritized phase
    def updatePhaseTimeSplit(origin_pts):

        # 例外處理: 兩組list長度不同
        class listLengthError(Exception):
            def __init__(self, cause, msg):
                self.cause = cause
                self.message = msg

            def __str__(self):
                return self.message + ' 原因: ' + self.cause

        #逐一比對
        try:
            if (len(origin_pts) == len(pts)):  # 檢查兩組list長度
                for num in range(len(origin_pts)):
                    if (origin_pts[num] != pts[num]):  # 找到不一致的
                        diff = pts[num] - origin_pts[num]  # 取出兩者差
                        for num_after in range(num+1, len(origin_pts)):
                            pts[num_after] = pts[num_after] + diff  # 更新: 把之後的全部加上diff
                        break

            else:
                raise listLengthError(cause='兩組list長度不同', msg='list length error')
        except listLengthError as err:
            print("Error message:  %s" %err)

        return pts

    def adjustPhaseDuration(a, b, RSU, currentPhase, numOfCycleToProcess, greenTag):
        # a -> non-prioritized phase (nonPP) / b -> prioritized phase (PP)
        cycle0_nonPP_ExtentAmount = 0
        cycle0_nonPP_TruncationAmount = 0
        cycle1_nonPP_ExtentAmount = 0
        cycle1_nonPP_TruncationAmount = 0

        cycle0_PP_ExtentAmount = 0
        cycle0_PP_TruncationAmount = 0
        cycle1_PP_ExtentAmount = 0
        cycle1_PP_TruncationAmount = 0


        def calPhase_MAX_EXTENT_and_TRUNCATE(cycleAmount, currentPhase,
                                             cycle0_nonPP_ExtentAmount, cycle0_nonPP_TruncationAmount, cycle1_nonPP_ExtentAmount , cycle1_nonPP_TruncationAmount,
                                             cycle0_PP_ExtentAmount, cycle0_PP_TruncationAmount, cycle1_PP_ExtentAmount, cycle1_PP_TruncationAmount):

            # 延長
            for phase in RSU.plan[appliedPlanNum].phases[currentPhase:]:  # 從currentPhase開始取出時相物件

                if (phase.IsAdjustable and phase.IsInUncontrollableStep == False):  # 先確認該phase是可以調整的

                    if (phase.phaseID == prioritizedPhase):  #遇到prioritizedPhase特別挑出
                        cycle0_PP_ExtentAmount = cycle0_PP_ExtentAmount + phase.EXTENT_LIMIT
                    else:  # phaseID != prioritizedPhase
                        cycle0_nonPP_ExtentAmount = cycle0_nonPP_ExtentAmount + phase.EXTENT_LIMIT

            # 切斷
            for phase in RSU.plan[appliedPlanNum].phases[currentPhase:]:  # 從currentPhase開始取出時相物件
                # 遇到currentPhase特別挑出: 避免違反Gmin條件，另需區分greentTag = 0 或 greenTag = 1 兩種狀況
                # 條件: 若phase的行閃>0 -> 則GminLimit=0不受限

                if (phase.IsAdjustable and phase.IsInUncontrollableStep == False):  # 先確認該phase是可以調整的

                    if phase.pedFlash > 0:
                        GminLimit = 0
                    else:
                        GminLimit = phase.Gmin

                    if (phase.phaseID == currentPhase and currentPhase == prioritizedPhase):

                        if (remainingTime >= GminLimit + abs(phase.TRUNCATION_LIMIT)):  # 1 剩餘秒數 >= 最短綠 + 時相最大允許切斷量
                            cycle0_PP_TruncationAmount = phase.TRUNCATION_LIMIT
                        elif ((GminLimit < remainingTime) and (remainingTime < GminLimit + abs(phase.TRUNCATION_LIMIT))):  # 2 最短綠 < 剩餘秒數 < 最短綠 + 時相最大允許切斷量
                            cycle0_PP_TruncationAmount = GminLimit - remainingTime
                        else:  # 3 remainingTime <= Gmin  剩餘秒數<最短綠 -> 不可切斷
                            cycle0_PP_TruncationAmount = 0

                    elif (phase.phaseID == currentPhase and currentPhase != prioritizedPhase):
                        if (remainingTime >= GminLimit + abs(phase.TRUNCATION_LIMIT)):  # 1 剩餘秒數 >= 最短綠 + 時相最大允許切斷量
                            cycle0_nonPP_TruncationAmount = phase.TRUNCATION_LIMIT
                        elif ((GminLimit < remainingTime) and (remainingTime < GminLimit + abs(phase.TRUNCATION_LIMIT))):  # 2 最短綠 < 剩餘秒數 < 最短綠 + 時相最大允許切斷量
                            cycle0_nonPP_TruncationAmount = GminLimit - remainingTime
                        else:  # 3 remainingTime <= Gmin  剩餘秒數<最短綠 -> 不可切斷
                            cycle0_nonPP_TruncationAmount = 0

                    else:  # 挑出的phase != currentPhase
                        if (phase.phaseID == prioritizedPhase):
                            cycle0_PP_TruncationAmount = cycle0_PP_TruncationAmount + phase.TRUNCATION_LIMIT
                        else:
                            cycle0_nonPP_TruncationAmount = cycle0_nonPP_TruncationAmount + phase.TRUNCATION_LIMIT


            if cycleAmount == 2:  # 需要調整兩個週期的，再新增下一個週期的調整量
            ## Cycle 1: 計算下個cycle各phase可以延長/切斷量 ##

                for phase in RSU.plan[appliedPlanNum].phases:

                    if (phase.IsAdjustable):  # 先確認該phase是可以調整的

                        if phase.phaseID != prioritizedPhase:  # 挑出非公車優先時相
                            cycle1_nonPP_ExtentAmount = cycle1_nonPP_ExtentAmount + phase.EXTENT_LIMIT  # 分別加總延長量
                            cycle1_nonPP_TruncationAmount = cycle1_nonPP_TruncationAmount + phase.TRUNCATION_LIMIT
                        else:  # phase.phaseID == prioritizedPhase: 挑出公車優先時相
                            cycle1_PP_ExtentAmount = phase.EXTENT_LIMIT
                            cycle1_PP_TruncationAmount = phase.TRUNCATION_LIMIT


            max_nonPP_TruncationAmount = cycle0_nonPP_TruncationAmount + cycle1_nonPP_TruncationAmount
            max_PP_TruncationAmount = cycle0_PP_TruncationAmount + cycle1_PP_TruncationAmount
            max_nonPP_ExtentAmount = cycle0_nonPP_ExtentAmount + cycle1_nonPP_ExtentAmount
            max_PP_ExtentAmount = cycle0_PP_ExtentAmount + cycle1_PP_ExtentAmount

            return cycle0_nonPP_TruncationAmount, cycle1_nonPP_TruncationAmount, cycle0_PP_TruncationAmount, cycle1_PP_TruncationAmount,\
                   cycle0_nonPP_ExtentAmount, cycle1_nonPP_ExtentAmount, cycle0_PP_ExtentAmount, cycle1_PP_ExtentAmount,\
                   max_nonPP_ExtentAmount, max_nonPP_TruncationAmount, max_PP_ExtentAmount, max_PP_TruncationAmount

        def compare_a_b_and_maxAdjAmount(a, b, max_nonPP_ExtentAmount, max_nonPP_TruncationAmount, max_PP_ExtentAmount, max_PP_TruncationAmount):
            if (a > 0 and b > 0):  # Extent non-prioritized phases + Extent prioritized phase
                # a,b不可超過時相延長限制
                nonPP_adjAmount = min(a, max_nonPP_ExtentAmount)
                PP_adjAmount = min(b, max_PP_ExtentAmount)
            elif (a > 0 and b <= 0):  # Extent non-prioritized phases + Truncate prioritized phase
                # a 不可大於非公車優先時相們的總延長限制, b 不可大於公車優先時相切斷限制
                nonPP_adjAmount = min(a, max_nonPP_ExtentAmount)
                PP_adjAmount = max(b, max_PP_TruncationAmount)

            elif (a <= 0 and b > 0):  # Truncate non-prioritized phases + Extent prioritized phase
                # a 不可大於非公車優先時相們的總切斷限制
                nonPP_adjAmount = max(a, max_nonPP_TruncationAmount)
                PP_adjAmount = min(b, max_PP_ExtentAmount)
            elif (a <= 0 and b <= 0):  # Truncate non-prioritized phases + Truncate prioritized phase
                nonPP_adjAmount = max(a, max_nonPP_TruncationAmount)
                PP_adjAmount = max(b, max_PP_TruncationAmount)

            else:
                nonPP_adjAmount = 0
                PP_adjAmount = 0
                print("exception error: a = ", a, " b = ", b)
                print(1 / 0)

            return nonPP_adjAmount, PP_adjAmount

        result = calPhase_MAX_EXTENT_and_TRUNCATE(cycle0_nonPP_ExtentAmount=cycle0_nonPP_ExtentAmount, cycle0_nonPP_TruncationAmount=cycle0_nonPP_TruncationAmount,
                                                  cycle1_nonPP_ExtentAmount=cycle1_nonPP_ExtentAmount, cycle1_nonPP_TruncationAmount=cycle1_nonPP_TruncationAmount,
                                                  cycle0_PP_ExtentAmount=cycle0_PP_ExtentAmount, cycle0_PP_TruncationAmount=cycle0_PP_TruncationAmount,
                                                  cycle1_PP_ExtentAmount=cycle1_PP_ExtentAmount, cycle1_PP_TruncationAmount=cycle1_PP_TruncationAmount,
                                                  cycleAmount=numOfCycleToProcess, currentPhase=currentPhase)

        cycle0_nonPP_TruncationAmount = result[0]
        cycle1_nonPP_TruncationAmount = result[1]
        cycle0_PP_TruncationAmount = result[2]
        cycle1_PP_TruncationAmount = result[3]
        cycle0_nonPP_ExtentAmount = result[4]
        cycle1_nonPP_ExtentAmount = result[5]
        cycle0_PP_ExtentAmount = result[6]
        cycle1_PP_ExtentAmount = result[7]

        result_AfterCompare = compare_a_b_and_maxAdjAmount(a=a, b=b, max_nonPP_ExtentAmount=result[8],
                                                           max_nonPP_TruncationAmount=result[9],
                                                           max_PP_ExtentAmount=result[10],
                                                           max_PP_TruncationAmount=result[11])

        nonPP_adjAmount = result_AfterCompare[0]
        PP_adjAmount = result_AfterCompare[1]

        # step3. 調整phaseTimeSplit
        if (numOfCycleToProcess == 1):

            #print("numOfCycleToProcess = 1 / nonPP_adjAmount = ", nonPP_adjAmount, " / PP_adjAmount = ", PP_adjAmount)

            if (greenTag == 0):

                origin_pts = copy.deepcopy(pts) #複製當下的pts到origin pts
                pts[1] = pts[1] + PP_adjAmount  # prioritized Phase adj 進行修改
                updatePhaseTimeSplit(origin_pts=origin_pts) #呼叫更新pts

                origin_pts = copy.deepcopy(pts)
                pts[2] = pts[2] + nonPP_adjAmount  # non-prioritized Phase adj
                updatePhaseTimeSplit(origin_pts=origin_pts)

            elif (greenTag == 1):

                origin_pts = copy.deepcopy(pts)  # 複製當下的pts到origin pts
                pts[1] = pts[1] + nonPP_adjAmount  # non-prioritized Phase adj
                updatePhaseTimeSplit(origin_pts=origin_pts)

                origin_pts = copy.deepcopy(pts)  # 複製當下的pts到origin pts
                pts[2] = pts[2] + PP_adjAmount  # prioritized Phase adj
                updatePhaseTimeSplit(origin_pts=origin_pts)

            else:
                print("green tag error, green tag = ", greenTag)
                print(1 / 0)

        elif (numOfCycleToProcess == 2):

             #print("cycleToProcess = 2 / nonPP_adjAmount = ", nonPP_adjAmount, " / PP_adjAmount = ", PP_adjAmount)
             if (greenTag == 0):

                if (b <= 0):  # Issue 3: 調整量照各週期可調量分配?

                    origin_pts = copy.deepcopy(pts)  # 複製當下的pts到origin pts

                    try:  # cycle 0, prioritized Phase adj
                        divisionResult = math.ceil(PP_adjAmount * abs(cycle0_PP_TruncationAmount) / (abs(cycle0_PP_TruncationAmount) + abs(cycle1_PP_TruncationAmount)))
                    except ZeroDivisionError:
                        divisionResult = 0

                    pts[1] = pts[1] + divisionResult
                    updatePhaseTimeSplit(origin_pts=origin_pts)

                    origin_pts = copy.deepcopy(pts)  # 複製當下的pts到origin pts
                    try:  # cycle 1, prioritized Phase adj
                        divisionResult = math.ceil(PP_adjAmount * abs(cycle1_PP_TruncationAmount) / (abs(cycle0_PP_TruncationAmount) + abs(cycle1_PP_TruncationAmount)))
                    except ZeroDivisionError:
                        divisionResult = 0

                    pts[3] = pts[3] + divisionResult
                    updatePhaseTimeSplit(origin_pts=origin_pts)

                else:
                    origin_pts = copy.deepcopy(pts)  # 複製當下的pts到origin pts
                    try:
                        divisionResult = math.ceil(PP_adjAmount * abs(cycle0_PP_ExtentAmount) / (abs(cycle0_PP_ExtentAmount) + abs(cycle1_PP_ExtentAmount)))  # cycle 0, prioritized Phase adj
                    except ZeroDivisionError:
                        divisionResult = 0
                    pts[1] = pts[1] + divisionResult
                    updatePhaseTimeSplit(origin_pts=origin_pts)

                    origin_pts = copy.deepcopy(pts)  # 複製當下的pts到origin pts
                    try:
                        divisionResult = math.ceil(PP_adjAmount * abs(cycle1_PP_ExtentAmount) / (abs(cycle0_PP_ExtentAmount) + abs(cycle1_PP_ExtentAmount)))  # cycle 1, prioritized Phase adj
                    except ZeroDivisionError:
                        divisionResult = 0
                    pts[3] = pts[3] + divisionResult
                    updatePhaseTimeSplit(origin_pts=origin_pts)

                if (a <= 0):
                    origin_pts = copy.deepcopy(pts)  # 複製當下的pts到origin pts
                    try:
                        divisionResult = math.ceil(nonPP_adjAmount * abs(cycle0_nonPP_TruncationAmount) / (abs(cycle0_nonPP_TruncationAmount) + abs(cycle1_nonPP_TruncationAmount)))  # cycle 0, prioritized Phase adj
                    except ZeroDivisionError:
                        divisionResult = 0
                    pts[2] = pts[2] + divisionResult
                    updatePhaseTimeSplit(origin_pts=origin_pts)

                    origin_pts = copy.deepcopy(pts)  # 複製當下的pts到origin pts
                    try:
                        divisionResult = math.ceil(nonPP_adjAmount * abs(cycle1_nonPP_TruncationAmount) / (abs(cycle0_nonPP_TruncationAmount) + abs(cycle1_nonPP_TruncationAmount)))  # cycle 1, prioritized Phase adj
                    except ZeroDivisionError:
                        divisionResult = 0
                    pts[4] = pts[4] + divisionResult
                    updatePhaseTimeSplit(origin_pts=origin_pts)

                else:
                    origin_pts = copy.deepcopy(pts)  # 複製當下的pts到origin pts
                    try:
                        divisionResult = math.ceil(nonPP_adjAmount * abs(cycle0_nonPP_ExtentAmount) / (abs(cycle0_nonPP_ExtentAmount) + abs(cycle1_nonPP_ExtentAmount)))  # cycle 0, prioritized Phase adj
                    except ZeroDivisionError:
                        divisionResult = 0
                    pts[2] = pts[2] + divisionResult
                    updatePhaseTimeSplit(origin_pts=origin_pts)

                    origin_pts = copy.deepcopy(pts)  # 複製當下的pts到origin pts
                    try:
                        divisionResult = math.ceil(nonPP_adjAmount * abs(cycle1_nonPP_ExtentAmount) / (abs(cycle0_nonPP_ExtentAmount) + abs(cycle1_nonPP_ExtentAmount)))  # cycle 1, prioritized Phase adj
                    except ZeroDivisionError:
                        divisionResult = 0
                    pts[4] = pts[4] + divisionResult
                    updatePhaseTimeSplit(origin_pts=origin_pts)

             elif (greenTag == 1):

                if (a <= 0):
                    origin_pts = copy.deepcopy(pts)  # 複製當下的pts到origin pts
                    try:
                        divisionResult = int(nonPP_adjAmount * abs(cycle0_nonPP_TruncationAmount) / (
                                    abs(cycle0_nonPP_TruncationAmount) + abs(cycle1_nonPP_TruncationAmount)))  # cycle 0, non-prioritized Phase adj
                    except ZeroDivisionError:
                        divisionResult = 0
                    pts[1] = pts[1] + divisionResult
                    updatePhaseTimeSplit(origin_pts=origin_pts)

                    origin_pts = copy.deepcopy(pts)  # 複製當下的pts到origin pts
                    try:
                        divisionResult = int(nonPP_adjAmount * abs(cycle1_nonPP_TruncationAmount) / (abs(cycle0_nonPP_TruncationAmount) + abs(cycle1_nonPP_TruncationAmount)))  # cycle 0, non-prioritized Phase adj
                    except ZeroDivisionError:
                        divisionResult = 0
                    pts[3] = pts[3] + divisionResult
                    updatePhaseTimeSplit(origin_pts=origin_pts)

                else:

                    origin_pts = copy.deepcopy(pts)  # 複製當下的pts到origin pts
                    try:
                        divisionResult = int(nonPP_adjAmount * abs(cycle0_nonPP_ExtentAmount) / (abs(cycle0_nonPP_ExtentAmount) + abs(cycle1_nonPP_ExtentAmount)))
                    except ZeroDivisionError:
                        divisionResult = 0

                    pts[1] = pts[1] + divisionResult
                    updatePhaseTimeSplit(origin_pts=origin_pts)

                    origin_pts = copy.deepcopy(pts)  # 複製當下的pts到origin pts
                    try:
                        divisionResult = int(nonPP_adjAmount * abs(cycle1_nonPP_ExtentAmount) / (abs(cycle0_nonPP_ExtentAmount) + abs(cycle1_nonPP_ExtentAmount)))
                    except ZeroDivisionError:
                        divisionResult = 0
                    pts[3] = pts[3] + divisionResult
                    updatePhaseTimeSplit(origin_pts=origin_pts)

                if (b <= 0):
                    origin_pts = copy.deepcopy(pts)  # 複製當下的pts到origin pts
                    try:
                        divisionResult = int(PP_adjAmount * abs(cycle1_PP_TruncationAmount) / (abs(cycle0_PP_TruncationAmount) + abs(cycle1_PP_TruncationAmount)))
                    except ZeroDivisionError:
                        divisionResult = 0
                    pts[2] = pts[2] + divisionResult
                    updatePhaseTimeSplit(origin_pts=origin_pts)

                else:  # b > 0
                    origin_pts = copy.deepcopy(pts)  # 複製當下的pts到origin pts
                    try:
                        divisionResult = int(PP_adjAmount * abs(cycle1_PP_ExtentAmount) / (abs(cycle0_PP_TruncationAmount) + abs(cycle1_PP_TruncationAmount)))
                    except ZeroDivisionError:
                        divisionResult = 0
                    pts[2] = pts[2] + divisionResult
                    updatePhaseTimeSplit(origin_pts=origin_pts)

             else:
                print("green tag error, gt = ", greenTag)
                print(1 / 0)


        return pts

    # Step 1. 判斷是否為切斷紅燈至最短方案:
    if (truncate_red_light_to_min == False):
        pts_Result = adjustPhaseDuration(a=a, b=b, RSU=RSU, currentPhase=currentPhase,
                                     greenTag=greenTag, numOfCycleToProcess=numOfCycleToProcess)

        return pts_Result

    elif (truncate_red_light_to_min == True):
        # 紅燈切斷至最短(不論numOfCycleToProcess為何，皆允許跨到兩週期)
        cycle0_nonPP_TruncationAmount = 0
        cycle1_nonPP_TruncationAmount = 0

        if (greenTag == 0): #目標: 將接著的紅燈切斷至最短(可能跨到cycle 1)
            for phase in RSU.plan[appliedPlanNum].phases[currentPhase+1:]:  # Cycle 0 : 設定從currentPhase的下一個phase開始取出phase物件
                if (phase.IsAdjustable and phase.IsInUncontrollableStep == False): #確認該時相可以調整
                    cycle0_nonPP_TruncationAmount = cycle0_nonPP_TruncationAmount + phase.TRUNCATION_LIMIT  #將所有非優先時相的最大切斷量一一加總
                else:
                    print("時相", phase.phaseID, "無法進行修改，跳過此時相!")

            for phase in RSU.plan[appliedPlanNum].phases[:currentPhase]:  # Cycle 1:從頭到currentPhase前屬於cycle 1的nonPP truncation amount
                if (phase.IsAdjustable):  # 確認該時相可以調整
                    cycle1_nonPP_TruncationAmount = cycle1_nonPP_TruncationAmount + phase.TRUNCATION_LIMIT  # 將所有非優先時相的最大切斷量一一加總
                else:
                    print("時相", phase.phaseID, "無法進行修改，跳過此時相!")

            if (numOfCycleToProcess == 1):
                origin_pts = copy.deepcopy(pts)  # 複製當下的pts到origin pts
                pts[2] = pts[2] + cycle0_nonPP_TruncationAmount  # 切斷cycle 0的紅燈至最短
                updatePhaseTimeSplit(origin_pts=origin_pts)  # 呼叫更新pts

            elif (numOfCycleToProcess == 2):

                origin_pts = copy.deepcopy(pts)  # 複製當下的pts到origin pts
                pts[2] = pts[2] + cycle0_nonPP_TruncationAmount  # 切斷cycle 0的紅燈至最短
                updatePhaseTimeSplit(origin_pts=origin_pts)  # 呼叫更新pts

                origin_pts = copy.deepcopy(pts)  # 複製當下的pts到origin pts
                pts[2] = pts[2] + cycle1_nonPP_TruncationAmount  # 切斷cycle 1的紅燈至最短
                updatePhaseTimeSplit(origin_pts=origin_pts)  # 呼叫更新pts

                # if (prioritizedPhase == RSU.plan[appliedPlanNum].phases[-1].phaseID):  # 若是時制內最後一個phase: pts[2] 是下一個cycle的
                #     origin_pts = copy.deepcopy(pts)  # 複製當下的pts到origin pts
                #     pts[2] = pts[2] + cycle1_nonPP_TruncationAmount  # 切斷cycle 1的紅燈至最短
                #     updatePhaseTimeSplit(origin_pts=origin_pts)  # 呼叫更新pts
                # else:
                #     origin_pts = copy.deepcopy(pts)  # 複製當下的pts到origin pts
                #     pts[2] = pts[2] + cycle0_nonPP_TruncationAmount  # 切斷cycle 0的紅燈至最短
                #     updatePhaseTimeSplit(origin_pts=origin_pts)  # 呼叫更新pts
            else:
                print(1/0)

        elif (greenTag == 1):  #目標: 將cycle 0的紅燈切斷至最短 (盡快提前cycle 0的綠燈)

            if (cp == RSU.plan[sp].phases[-1].phaseID and pp == RSU.plan[sp].phases[0].phaseID): # 特殊狀況
                phase = RSU.plan[sp].phases[-1]
                if (phase.IsAdjustable and phase.IsInUncontrollableStep == False):
                    # 條件: 若phase的行閃>0 -> 則GminLimit=0不受限
                    if phase.pedFlash > 0:
                        GminLimit = 0
                    else:
                        GminLimit = phase.Gmin

                    if (remainingTime >= GminLimit + abs(phase.TRUNCATION_LIMIT)):  # 1 剩餘秒數 >= 最短綠 + 時相最大允許切斷量
                        cycle0_nonPP_TruncationAmount = cycle0_nonPP_TruncationAmount + phase.TRUNCATION_LIMIT
                    elif ((GminLimit < remainingTime) and (
                            remainingTime < GminLimit + abs(phase.TRUNCATION_LIMIT))):  # 2 最短綠 < 剩餘秒數 < 最短綠 + 時相最大允許切斷量
                        cycle0_nonPP_TruncationAmount = cycle0_nonPP_TruncationAmount + GminLimit - remainingTime
                    else:  # 3 remainingTime <= Gmin  剩餘秒數<最短綠 -> 不可切斷
                        cycle0_nonPP_TruncationAmount = cycle0_nonPP_TruncationAmount + 0

            else:
                for phase in RSU.plan[appliedPlanNum].phases[currentPhase:prioritizedPhase]:  # 從currentPhase開始依序取出phase物件，直到prioritizedPhase的前一個phase
                    # 切斷非優先時相至最短: 分為 (1) 當下運作時相 (2) 非當下運作時相
                    if (phase.IsAdjustable and phase.IsInUncontrollableStep == False):
                        # 條件: 若phase的行閃>0 -> 則GminLimit=0不受限
                        if phase.pedFlash > 0:
                            GminLimit = 0
                        else:
                            GminLimit = phase.Gmin

                        if (phase.phaseID == currentPhase):  # 時相編號是當下運作時相
                            if (remainingTime >= GminLimit + abs(phase.TRUNCATION_LIMIT)):  # 1 剩餘秒數 >= 最短綠 + 時相最大允許切斷量
                                cycle0_nonPP_TruncationAmount = cycle0_nonPP_TruncationAmount + phase.TRUNCATION_LIMIT
                            elif ((GminLimit < remainingTime) and (remainingTime < GminLimit + abs(phase.TRUNCATION_LIMIT))):  # 2 最短綠 < 剩餘秒數 < 最短綠 + 時相最大允許切斷量
                                cycle0_nonPP_TruncationAmount = cycle0_nonPP_TruncationAmount + GminLimit - remainingTime
                            else:  # 3 remainingTime <= Gmin  剩餘秒數<最短綠 -> 不可切斷
                                cycle0_nonPP_TruncationAmount = cycle0_nonPP_TruncationAmount + 0
                        else:  # 時相編號不是當下運作時相
                            cycle0_nonPP_TruncationAmount = cycle0_nonPP_TruncationAmount + phase.TRUNCATION_LIMIT


            if (cycle0_nonPP_TruncationAmount == 0):
                # 特殊狀況 表示: (1)優先時相的前一個時相即為當下運作時相，且(2)符合不執行切斷條件: 1. phase.IsAdjustable = False 或 2. 已進入最短綠
                print("非優先時相僅一組且為當下時相，並符合不執行切斷條件，無法再切斷！")
                return False
            else:
                origin_pts = copy.deepcopy(pts)  # 複製當下的pts到origin pts
                pts[1] = pts[1] + cycle0_nonPP_TruncationAmount  # 切斷紅燈至最短
                updatePhaseTimeSplit(origin_pts=origin_pts)  # 呼叫更新pts

        return pts

    else:
        # 非 切斷紅燈至最短 方案
        return False

shiftAdjAmount = [0, 0, 0, 0, 0, 0, 0, 0]
def makeOutputFile(sp, dist, cp, rt, rt_before_step2, pp, RSU, fF, originPTS, finalPTS, greenTag, numOfCycleToProcess):
    # 先將column寫入csv檔
    import csv
    import os.path

    from datetime import date
    today = date.today()
    todayDate = today.strftime("%Y%m%d")

    filePath = OUTPUT_FILE_PATH + '/S428901   _' + str(sp+1) + '_' + todayDate + '.csv'

    if os.path.isfile(filePath):
        print("File exist")
        # f = open(filePath, 'r+')
        # f.truncate(0)
        pass
    else:
        print("File not exist")
        #第一次使用檔案，先寫入headColumn
        if OUTPUT_WITH_INPUT_COLUMN:
            column = ['Distance', 'Current_Signal_Phase', 'Remaining_Time', 'Target_Phase']
        else:
            column = []

        output_column = []

        for c in [0, 1]:  # 兩個週期
            for phase in range(0, 8, 1):
                output_column.append('c' + str(c) + 'p' + str(phase + 1))

        column.extend(output_column)

        with open(filePath, 'w+', newline='') as csvfile:
            writer = csv.writer(csvfile)
            writer.writerow(column)

        csvfile.close()

    # 建立各時相調整量
    phaseAdjAmountDict = {'Cycle0': {}, 'Cycle1': {}}
    phaseEffectTimeDict = {'Cycle0': {}, 'Cycle1': {}}

    #新增紀錄各分相的內容
    for phaseID in range(0, 8, 1): #0~8 phase
        #if (phase.IsAdjustable):  # 若時相 extent and truncation limit = 0則不列入計算
            #phaseSplitRatio.append(round(phase.greenSplit/ratioDenominator, 2)) #四捨五入到小數第2位
            for cycle in phaseAdjAmountDict: #各分相先記錄為0
                phaseAdjAmountDict[cycle].update({phaseID: 0}) #phase.phaseID

    #alreadyAdjFlag = False  # 用於標記是否已經調整過 (注意!!! 此變數設置原因乃假設只有調整either nonPP or PP，沒有兩者都調的情況)

    # 計算各分相調整量
    if (fF == True):
        print("時相已進入最短綠，無調整方案！")
    elif (numOfCycleToProcess == 0):
        print("通過機率足夠，不用修改秒數!")
    elif (greenTag == 0 and numOfCycleToProcess == 1):
        # greenTag = 0 --> [(0) 綠燈  (1) 綠燈結束, (2) 綠燈開始, (3)綠燈結束,..., (n)綠燈開始 (n+1) 綠燈結束]
        for num in range(1, 3):
            if (num == 1 and finalPTS[1] != originPTS[1]):
                adjAmount = finalPTS[num] - originPTS[num]  # 計算差異量
                #當下時相(=優先時相)延長or縮短
                phaseAdjAmountDict['Cycle0'][cp] = adjAmount
            elif (num == 2 and (finalPTS[2] - finalPTS[1]) != (originPTS[2] - originPTS[1]) ): #非當下時相延長or縮短

                adjAmount = (finalPTS[2] - finalPTS[1]) - (originPTS[2] - originPTS[1])
                ratioDenominator = 0
                # 計算ratioDenominator: 將cp之後所有phase的green加總，作為之後分配調整量的分母ratioDenominator(若時相 extent and truncation limit = 0則不列入計算)
                for phase in RSU.plan[sp].phases[cp+1:]: #從當下時相的下一個時相依序取出phase物件
                    if (phase.IsAdjustable and phase.IsInUncontrollableStep == False): # 若時相 extent and truncation limit = 0則不列入計算
                        ratioDenominator = ratioDenominator + phase.green

                for phase in RSU.plan[sp].phases[cp+1:]: #依序取出phase物件
                    if (phase.IsAdjustable and phase.IsInUncontrollableStep == False):
                        # 若時相 extent and truncation limit = 0則不列入計算
                        # 照時比分配調整秒數到各時相
                        phaseAdjAmountDict['Cycle0'][phase.phaseID] = math.ceil(adjAmount * (phase.green/ratioDenominator))

    elif (greenTag == 1 and numOfCycleToProcess == 1):
        # greenTag = 1 -->  # [(0) 綠燈尚未開始(紅燈)  (1) 綠燈開始, (2) 綠燈結束, (3)綠燈開始,..., (n)綠燈結束]
        for num in range(1, 3): #1~2
            if (num == 1 and finalPTS[1] != originPTS[1]): #非優先時相們要延長or縮短
                adjAmount = finalPTS[1] - originPTS[1]  # 計算差異量
                ratioDenominator = 0
                # 計算ratioDenominator: 將cp之後所有phase的green加總，作為之後分配調整量的分母ratioDenominator(若時相 extent and truncation limit = 0則不列入計算)

                if (pp < cp):
                    final = 99999
                else:
                    final = pp

                for phase in RSU.plan[sp].phases[cp:final]:  # 依序取出phase物件，直到pp的前一個phase
                    if (phase.IsAdjustable and phase.IsInUncontrollableStep == False):  # 若時相 extent and truncation limit = 0則不列入計算
                        ratioDenominator = ratioDenominator + phase.green

                for phase in RSU.plan[sp].phases[cp:final]:  # 依序取出phase物件
                    if (phase.IsAdjustable and phase.IsInUncontrollableStep == False):

                        # 原則: 照時比分配調整秒數到各時相
                        if (phase.phaseID == cp and adjAmount < 0):  # 遇到cp且是縮短時相的話，需特別處理:

                            # 條件: 若phase的行閃>0 -> 則GminLimit=0不受限
                            if phase.pedFlash > 0:
                                GminLimit = 0
                            else:
                                GminLimit = phase.Gmin

                            phaseAdjAmountDict['Cycle0'][phase.phaseID] = max(GminLimit - rt, math.ceil(adjAmount * (phase.green / ratioDenominator)))
                        else:  # 其餘狀況照原則操作即可
                            phaseAdjAmountDict['Cycle0'][phase.phaseID] = math.ceil(adjAmount * (phase.green / ratioDenominator))

            elif (num == 2 and (originPTS[2] - originPTS[1]) != (finalPTS[2] - finalPTS[1])):
                adjAmount = (finalPTS[2] - finalPTS[1]) - (originPTS[2] - originPTS[1]) #與原始長度比較，計算差異量
                phaseAdjAmountDict['Cycle0'][pp] = adjAmount

    elif (greenTag == 0 and numOfCycleToProcess == 2):
        print("xxx")
        for num in range(1, 5): #1~4
            if (num == 1 and originPTS[1] != finalPTS[1]):
                adjAmount = finalPTS[1] - originPTS[1]
                phaseAdjAmountDict['Cycle0'][cp] = adjAmount  # 修改cycle 0的現在時相(=優先時相)

            elif (num == 2 and (originPTS[2] - originPTS[1]) != (finalPTS[2] - finalPTS[1])):
                adjAmount = (finalPTS[2] - finalPTS[1]) - (originPTS[2] - originPTS[1])

                import itertools
                phasePool = itertools.cycle(RSU.plan[sp].phases)
                revisedPhasePool = itertools.islice(phasePool, cp+1, None)  # 設定從currentPhase的下一個phase開始取出phase物件
                ratioDenominator = 0
                # 計算ratioDenominator: 將cp之後所有phase的green加總，作為之後分配調整量的分母ratioDenominator(若時相 extent and truncation limit = 0則不列入計算)
                for phase in revisedPhasePool:  # 依序取出phase物件
                    if (phase.phaseID == pp):  # 繞一圈到prioritizedPhase結束
                        break
                    if (phase.IsAdjustable):  # 若時相 extent and truncation limit = 0則不列入計算
                        ratioDenominator = ratioDenominator + phase.green

                for phase in revisedPhasePool:  # 依序取出phase物件
                    if (phase.phaseID == pp):  # 繞一圈到prioritizedPhase結束
                        break
                    if (phase.IsAdjustable):
                        # 若時相 extent and truncation limit = 0則不列入計算
                        # 照時比分配調整秒數到各時相:
                        if (phase.phaseID < pp):  # 注意! phaseID < pp 開始需要分配到cycle 1來做調整!
                            phaseAdjAmountDict['Cycle1'][phase.phaseID] = math.ceil(adjAmount * (phase.green / ratioDenominator))
                        else:
                            if (phase.IsInUncontrollableStep == False):
                                phaseAdjAmountDict['Cycle0'][phase.phaseID] = math.ceil(adjAmount * (phase.green / ratioDenominator))


            elif (num == 3 and originPTS[3] != finalPTS[3] and finalPTS[3] - finalPTS[2] != originPTS[3] - originPTS[2]):
                adjAmount = (finalPTS[3] - finalPTS[2]) - (originPTS[3] - originPTS[2])
                phaseAdjAmountDict['Cycle1'][pp] = adjAmount  # 修改cycle 1的優先時相

            elif (num == 4 and originPTS[4] != finalPTS[4] and finalPTS[4] - finalPTS[3] != originPTS[4] - originPTS[3]):
                adjAmount = (finalPTS[4] - finalPTS[3]) - (originPTS[4] - originPTS[3])
                #### function ####
                ratioDenominator = sum([phase.green for phase in RSU.plan[sp].phases[pp+1:]
                                        if (phase.IsAdjustable)])

                for phase in RSU.plan[sp].phases[pp+1:]:
                    if (phase.IsAdjustable):
                        # 照時比分配調整秒數到各時相
                        phaseAdjAmountDict['Cycle1'][phase.phaseID] = math.ceil(adjAmount * (phase.green / ratioDenominator))
                #### function ####

    elif (greenTag == 1 and numOfCycleToProcess == 2):
        print("yyy")
        import itertools
        phasePool = itertools.cycle(RSU.plan[sp].phases)
        revisedPhasePool = itertools.islice(phasePool, cp, None)  # 設定從currentPhase開始取出phase物件
        ratioDenominator = 0
        adjAmount = 0

        for num in range(1, 4): #1~3
            if (num == 1 and originPTS[1] != finalPTS[1]):
                adjAmount = (finalPTS[1] - originPTS[1])  # 計算差異量
                ratioDenominator = 0
                # 計算ratioDenominator: 將cp之後所有phase的green加總，作為之後分配調整量的分母ratioDenominator(若時相 extent and truncation limit = 0則不列入計算)

                if (cp == RSU.plan[sp].phases[-1].phaseID and pp == RSU.plan[sp].phases[0].phaseID):
                    phase = RSU.plan[sp].phases[-1]
                    if (adjAmount < 0): #縮短秒數: 考慮到Gmin問題

                        # 條件: 若phase的行閃>0 -> 則GminLimit=0不受限
                        if phase.pedFlash > 0:
                            GminLimit = 0
                        else:
                            GminLimit = phase.Gmin

                        phaseAdjAmountDict['Cycle0'][phase.phaseID] = max(GminLimit - rt, adjAmount)
                    else:
                        phaseAdjAmountDict['Cycle0'][phase.phaseID] = adjAmount

                else:

                    if (pp < cp):
                        final = 99999
                    else:
                        final = pp

                    for phase in RSU.plan[sp].phases[cp:final]:  # 依序取出phase物件，直到pp的前一個phase
                        if (phase.IsAdjustable and phase.IsInUncontrollableStep == False):  # 若時相 extent and truncation limit = 0則不列入計算
                            ratioDenominator = ratioDenominator + phase.green

                    for phase in RSU.plan[sp].phases[cp:final]:  # 依序取出phase物件
                        if (phase.IsAdjustable and phase.IsInUncontrollableStep == False):
                            # 若時相 extent and truncation limit = 0則不列入計算
                            # 原則: 照時比分配調整秒數到各時相
                            if (phase.phaseID == cp and adjAmount < 0):  # 遇到cp且是縮短時相的話，需特別處理:

                                # 條件: 若phase的行閃>0 -> 則GminLimit=0不受限
                                if phase.pedFlash > 0:
                                    GminLimit = 0
                                else:
                                    GminLimit = phase.Gmin

                                phaseAdjAmountDict['Cycle0'][phase.phaseID] = max(GminLimit - rt, math.ceil(adjAmount * (phase.green / ratioDenominator)))
                            else:  # 其餘狀況照原則操作即可
                                phaseAdjAmountDict['Cycle0'][phase.phaseID] = math.ceil(adjAmount * (phase.green / ratioDenominator))

            elif (num == 2 and originPTS[2] != finalPTS[2] and (originPTS[2] - originPTS[1]) != (finalPTS[2] - finalPTS[1])):
                #條件: (1) originPTS[2] != finalPTS[2] 而且 (2) 和預計綠燈長度不一樣 表示cycle 0的優先時相有被修改!
                adjAmount = (finalPTS[2] - finalPTS[1]) - (originPTS[2] - originPTS[1])
                # 特別狀況: 若pp<cp -> 修改cycle1的adjAmount
                if (pp < cp):
                    phaseAdjAmountDict['Cycle1'][pp] = adjAmount
                else:  # 否則: 修改 cycle 0 的優先時相
                    phaseAdjAmountDict['Cycle0'][pp] = adjAmount

            elif (num == 3 and originPTS[3] != finalPTS[3] and (originPTS[3] - originPTS[2]) != (finalPTS[3] - finalPTS[2])):
                adjAmount = (finalPTS[3] - finalPTS[2]) - (originPTS[3] - originPTS[2])
                # [0]---紅燈---[1]---綠燈---[2]---紅燈---[3]

                ratioDenominator = 0
                # 計算ratioDenominator: 將cp之後所有phase的green加總，作為之後分配調整量的分母ratioDenominator(若時相 extent and truncation limit = 0則不列入計算)

                if (pp == RSU.plan[sp].phases[0].phaseID):  # pp是起頭時相
                    phaseInterator = RSU.plan[sp].phases[pp+1:]
                else: phaseInterator = RSU.plan[sp].phases[0:pp]

                for phase in phaseInterator:
                    if (phase.IsAdjustable):
                        # 逐一取出將非pp時相加總
                        ratioDenominator = ratioDenominator + phase.green
                for phase in phaseInterator:
                    if (phase.IsAdjustable):
                        # 照時比分配調整秒數到各時相:
                        phaseAdjAmountDict['Cycle1'][phase.phaseID] = math.ceil( adjAmount * (phase.green / ratioDenominator))


    else:
        print("待完成")
        print(1/0)

    print("originPTS = ", originPTS)
    print("finalPTS = ", finalPTS)
    print("phaseAdjAmount = ", phaseAdjAmountDict)

    cumulatedAdjAmount = 0
    with open(filePath, 'a', newline='\n') as csvfile:
        writer = csv.writer(csvfile)

        if OUTPUT_WITH_INPUT_COLUMN:
            input = [dist, cp + 1, rt, pp + 1]
        else:
            input = []

        for cycle in ['Cycle0', 'Cycle1']:
            for phaseID in range(0, 8, 1):
                if (cycle == 'Cycle0' and cp == pp and phaseID == cp):  #cp == pp -> 時相綠燈
                    if (rt_before_step2 < 5):
                        shiftAdjAmount[phaseID] = shiftAdjAmount[phaseID] + phaseAdjAmountDict[cycle][phaseID]
                        input.append(0)
                    elif (rt_before_step2 == 5): #把步階1剩餘秒數1~5秒時的調整秒數統一移動到第5秒
                        input.append(shiftAdjAmount[phaseID] + phaseAdjAmountDict[cycle][phaseID])
                        shiftAdjAmount[phaseID] = 0
                    else:
                        input.append(phaseAdjAmountDict[cycle][phaseID])
                else:
                    input.append(phaseAdjAmountDict[cycle][phaseID])

        print("input = ", input)
        writer.writerow(input)

    csvfile.close()

    return 0


M = 9999999
greentag = 0

tempPassProb = 0
newPassProb = 0
nonPrioritizedPhase_Adjustment = 0
PrioritizedPhase_Adjustment = 0
phaseTimeSplit = 0
newPhaseTimeSplit = 0
finalPhaseTimeSplit = []

success_count = 0
fail_count = 0

if ASSIGENED_PLAN_NUM == 0:
    SIGNALPLAN = range(planNum)
else:
    SIGNALPLAN = [ASSIGENED_PLAN_NUM - 1]

DIST = range(10, 510, 10)

#開始運算

for sp in SIGNALPLAN:

    #CURRENT_PHASE = range(0, len(RSUs['rsu1'].plan[sp].phases), 1)  # len(RSUs['rsu1'].plan[sp].phases)
    CURRENT_PHASE = range(0, 8, 1)

    #PRIORITIZED_PHASE = range(0, len(RSUs['rsu1'].plan[sp].phases), 1)
    PRIORITIZED_PHASE = range(0, 8, 1)

    for dist in DIST:
        for speed in SPEED:
            for cp in CURRENT_PHASE:
                REMAINING_TIME = range(1, 200, 2)
                for rt in REMAINING_TIME:
                    # 特別說明：(1) 控制器的rt指 剩餘綠燈 + 行閃 + 行紅 + 黃燈 + 全紅
                    #           (2) 本程式rt指 剩餘綠燈秒數
                    # 綜合以上兩者需進行判斷轉換
                    # rt_for_passProb = 用於計算通過機率的rt
                    # rt_for_calStrategy = 用於計算優先策略的rt

                    rt_for_resume = rt  # 備份rt

                    for pp in PRIORITIZED_PHASE:

                        if ((cp not in range(0, len(RSUs['rsu1'].plan[sp].phases), 1)) or
                                (pp not in range(0, len(RSUs['rsu1'].plan[sp].phases), 1)) or (dist >= 300)):
                            makeOutputFile(sp=sp, dist=dist, cp=cp, rt=rt, rt_before_step2=rt, pp=pp, RSU=RSUs['rsu1'], fF=True,
                                           originPTS=[], finalPTS=[], greenTag=0, numOfCycleToProcess=1)

                        else:
                            # # reset setIsInUncontrollableStep as TRUE
                            # for phase in RSUs['rsu1'].plan[sp].phases:
                            #     phase.setIsInUncontrollableStep(False)

                            #if (pp == cp):
                                # redRemainTime = 行閃 + 行紅 + 黃燈 + 全紅的秒數
                                # 因為控制器只修改步階1的秒數，因此步階2(行閃)也列入redRemainTime

                            pedFlash = RSUs['rsu1'].plan[sp].phases[cp].pedFlash
                            pedRed = RSUs['rsu1'].plan[sp].phases[cp].pedRed
                            yellow = RSUs['rsu1'].plan[sp].phases[cp].yellow
                            allRed = RSUs['rsu1'].plan[sp].phases[cp].allRed

                            redRemainTime = pedFlash + pedRed + yellow + allRed

                            if (redRemainTime < rt):  # 若rt > redRemainTime 則表示步階1還有秒數剩餘，仍然可以調整!
                                print("rt = ", rt, " > redRemainTime = ", redRemainTime, " 步階1還有秒數剩餘，仍然可以調整!")
                                rt_for_passProb = rt - (allRed + yellow + pedRed)  # 用於計算通過機率
                                rt_for_calStrategy = rt - redRemainTime  # 用於計算策略

                                RSUs['rsu1'].plan[sp].phases[cp].setIsInUncontrollableStep(False)

                            elif ((allRed + yellow + pedRed) < rt and rt <= redRemainTime):  # 進入行閃階段，步階1無法調整!
                                print("rt = ", rt, " redRemainTime = ", redRemainTime, " 步階1無法調整!")
                                rt_for_passProb = rt - (allRed + yellow + pedRed)
                                rt_for_calStrategy = 0

                                RSUs['rsu1'].plan[sp].phases[cp].setIsInUncontrollableStep(True)  # 步階1無法調整 -> 將IsInUncontrollableStep設定True -> 使計算調整秒數時不去動他

                            else:
                                print("rt = ", rt, " redRemainTime = ", redRemainTime, " 步階1無法調整!")
                                rt_for_passProb = 0  # 若rt <= redRemainTime 則表示已進入紅燈時間 -> 約略等於 rt=0
                                rt_for_calStrategy = 0
                                RSUs['rsu1'].plan[sp].phases[cp].setIsInUncontrollableStep(True)  # 步階1無法調整 -> 將IsInUncontrollableStep設定True -> 使計算調整秒數時不去動他


                            failFlag = False
                            print("*******************************************************************")
                            print("sp = ", sp, "dist = ", dist, "speed = ", speed, "cp = ", cp, "rt = ", rt,
                                  "rt_for_passProb = ", rt_for_passProb, "rt_for_calStrategy = ", rt_for_calStrategy,
                                  "pp = ", pp)

                            result = RSUs['rsu1'].calPhaseTimeSplit_NEW(appliedPlanNum=sp, targetPhase=pp, currentPhase=cp,
                                                                        remainingTime_gt0=rt_for_passProb, remainingTime_gt1=rt)
                            phaseTimeSplit = result[0]
                            greentag = result[1]
                            print("phaseTimeSplit = ", phaseTimeSplit)
                            print("greenTag = ", greentag)

                            # if (sp == 0 and dist == 110 and speed == 10 and cp == 1 and rt == 1 and pp == 1):
                            #     print("xxxxx")  # for debug

                            travelTime = dist / speed
                            passProb = calPassProb(dist=dist, arrivalTime=travelTime, phaseTimeSplit=phaseTimeSplit, greenTag=greentag)

                            # Step 1. 先把phaseTimeSplit備份一份
                            import copy
                            original_pts = copy.deepcopy(phaseTimeSplit)
                            print("origin phase time split = ", original_pts)

                            if (passProb < Thr):    # 通過機率小於門檻值

                                numOfCycleToProcess = RSUs['rsu1'].cal_NumOfCycleToProcess_NEW(dist=dist, speed=speed, arrivalTime=0, cp=cp, rt=rt_for_passProb, sp=sp)

                                NON_PRIORITIZED_PHASE_ADJ_LIMIT = round(sum(phase.green for phase in RSUs['rsu1'].plan[sp].phases if phase.phaseID != pp) * MAX_ADJUST_RATIO)
                                PRIORITIZED_PHASE_ADJ_LIMIT = round(RSUs['rsu1'].plan[sp].phases[pp].green * MAX_ADJUST_RATIO)

                                totalAdjustment = M

                                # a-> 非公車優先時相調整量  b-> 公車優先時相調整量

                                if (numOfCycleToProcess < 2):
                                    non_prioritized_phase_adj_range = range(-numOfCycleToProcess * NON_PRIORITIZED_PHASE_ADJ_LIMIT, 0)
                                    prioritized_phase_adj_range = range(0, numOfCycleToProcess * PRIORITIZED_PHASE_ADJ_LIMIT)
                                else:
                                    non_prioritized_phase_adj_range = range(-numOfCycleToProcess * NON_PRIORITIZED_PHASE_ADJ_LIMIT, numOfCycleToProcess * NON_PRIORITIZED_PHASE_ADJ_LIMIT)
                                    prioritized_phase_adj_range = range(-numOfCycleToProcess * PRIORITIZED_PHASE_ADJ_LIMIT, numOfCycleToProcess * PRIORITIZED_PHASE_ADJ_LIMIT)

                                for a in non_prioritized_phase_adj_range:
                                    for b in prioritized_phase_adj_range:

                                        phaseTimeSplit_result = Algorithm2_1(RSU=RSUs['rsu1'], pts=phaseTimeSplit, greenTag=greentag, a=a, b=b, numOfCycleToProcess=numOfCycleToProcess,
                                                     appliedPlanNum=sp, prioritizedPhase=pp, currentPhase=cp, remainingTime=rt_for_calStrategy, truncate_red_light_to_min=False)
                                        phaseTimeSplit = copy.deepcopy(original_pts)  # phaseTimeSplit回復到原始時制
                                        #print("優先控制 phaseTimeSplit_result = ", phaseTimeSplit_result)
                                        tempPassProb = calPassProb(dist=dist, arrivalTime=travelTime, phaseTimeSplit=phaseTimeSplit_result, greenTag=greentag)

                                        if (tempPassProb >= Thr):
                                            #print("優先控制11111")
                                            if (abs(a) + abs(b)) < totalAdjustment:
                                                totalAdjustment = abs(a) + abs(b)
                                                nonPrioritizedPhase_Adjustment = a
                                                PrioritizedPhase_Adjustment = b
                                                newPassProb = tempPassProb
                                                newPhaseTimeSplit = phaseTimeSplit_result

                                if totalAdjustment != M:
                                    print("========== 有找到優先控制方案！ ===========")
                                    print("sp = ", sp, "dist = ", dist, "speed = ", speed, "cp = ", cp,
                                          "rt_for_passProb = ", rt_for_passProb, "rt_for_calStrategy = ", rt_for_calStrategy, "pp = ", pp, "greenTag = ", greentag)
                                    print("originalPhaseTimeSplit = ", phaseTimeSplit)
                                    print("phaseTimeSplit Result = ", newPhaseTimeSplit)
                                    print("原始通過機率 = ", round(passProb, 4), "調整後通過機率 = ", newPassProb, "非優先時相總調整量 = ", nonPrioritizedPhase_Adjustment,
                                          " 優先時相調整量 = ", PrioritizedPhase_Adjustment)
                                    success_count = success_count + 1
                                    print("success_count = ", success_count)
                                    finalPhaseTimeSplit = newPhaseTimeSplit
                                    if (nonPrioritizedPhase_Adjustment != 0 and greentag == 0):
                                        print("xxxx") # for debug

                                else:
                                    # plan B: 嘗試紅燈切斷至最短
                                    phaseTimeSplit_result = Algorithm2_1(RSU=RSUs['rsu1'], truncate_red_light_to_min=True, pts=phaseTimeSplit,
                                                                         greenTag=greentag, a=0, b=0, numOfCycleToProcess=numOfCycleToProcess,
                                                                         appliedPlanNum=sp, prioritizedPhase=pp, currentPhase=cp, remainingTime=rt_for_calStrategy)
                                    phaseTimeSplit = copy.deepcopy(original_pts)  # phaseTimeSplit回復到原始時制
                                    if (phaseTimeSplit_result != False):
                                        finalPassProb = calPassProb(dist=dist, arrivalTime=travelTime, phaseTimeSplit=phaseTimeSplit_result, greenTag=greentag)
                                        print("========== 切斷紅燈至最短！ ==============")
                                        print("sp = ", sp, "dist = ", dist, "speed = ", speed, "cp = ", cp,
                                              "rt_for_passProb = ", rt_for_passProb, "rt_for_calStrategy = ", rt_for_calStrategy,
                                              "pp = ", pp, "greenTag = ", greentag)
                                        print("originalPhaseTimeSplit = ", phaseTimeSplit)
                                        print("phaseTimeSplit Result = ", phaseTimeSplit_result)
                                        print("原始通過機率 = ", round(passProb, 4), "調整後通過機率 = ", finalPassProb,
                                              "非優先時相總調整量 = ", (phaseTimeSplit_result[1] - phaseTimeSplit[1]) if greentag == 1 else (phaseTimeSplit_result[2] - phaseTimeSplit[2]))
                                        success_count = success_count + 1
                                        print("success_count = ", success_count)
                                        finalPhaseTimeSplit = phaseTimeSplit_result

                                    else:
                                        print("沒有可行解!")
                                        fail_count = fail_count + 1
                                        print("fail_count = ", fail_count)
                                        failFlag = True
                                        finalPhaseTimeSplit = 0

                            else:  # 通過機率足夠，不用更動號誌
                                print("========== 通過機率足夠！ 不用更動號誌 ==============")
                                print("sp = ", sp, "dist = ", dist, "speed = ", speed, "cp = ", cp,
                                      "rt_for_passProb = ", rt_for_passProb, "rt_for_calStrategy = ", rt_for_calStrategy,
                                      "pp = ", pp, "greenTag = ", greentag)
                                print("originalPhaseTimeSplit = ", phaseTimeSplit)
                                print("原始通過機率 = ", round(passProb, 4))
                                finalPhaseTimeSplit = phaseTimeSplit
                                numOfCycleToProcess = 0


                            makeOutputFile(sp=sp, dist=dist, cp=cp, rt=rt, rt_before_step2=rt_for_calStrategy, pp=pp, RSU=RSUs['rsu1'],
                                           fF=failFlag, originPTS=original_pts, finalPTS=finalPhaseTimeSplit, greenTag=greentag,
                                           numOfCycleToProcess=numOfCycleToProcess)



print("--- 執行共花了 %s seconds ---" % (time.time() - start_time))

