
import RSU
import SignalPlan
import math
import configparser
import copy
import argparse
import os
import sys

from scipy.stats import norm
from distutils.util import strtobool

import time
start_time = time.time()

class CloudControl():

    def __init__(self, SP, planParameters):
        self.SignalPlan = SP
        self.planParameters = planParameters

        # Config File Parser
        config = configparser.ConfigParser()
        path = '/'.join((os.path.abspath(__file__).replace('\\', '/')).split('/')[:-1])
        config.read(os.path.join(path, 'Config.ini'))
        # config = configparser.ConfigParser()
        # config.read('Config.ini')
        ###### Global Parameters ######
        self.MAX_ADJUST_RATIO = float(config['DEFAULT']['MAX_ADJUST_RATIO'])
        self.SPEED = int(config['DEFAULT']['SPEED'])
        self.Thr = float(config['DEFAULT']['PASS_PROBABILITY_Threshold'])
        self.RSUs = dict()

        if (int(config['OPTIONS']['STD_PRINT']) == 0):
            sys.stdout = open(os.devnull, 'w')
        else:
            sys.stdout = sys.__stdout__

    def setPhaseObject(self, i, inputPlan, planID, phaseOrder, offset):
        #I = RSU物件

        inputPlanLength = len(inputPlan)
        PhaseObjectList = []


        # Phase實體化，並加入PhaseObjectList
        for phase in range(0, inputPlanLength):
            PhaseObjectList.append(SignalPlan.Phase(phaseID=inputPlan[phase]['phaseID'], startTime=inputPlan[phase]['startTime'],
                                                    greenSplit=inputPlan[phase]['greenSplit'],green=inputPlan[phase]['green'], yellow=inputPlan[phase]['yellow'],
                                                    allRed=inputPlan[phase]['allRed'], Gmin=inputPlan[phase]['Gmin'], Gmax=inputPlan[phase]['Gmax'], pedFlash=inputPlan[phase]['pedFlash'],
                                                    pedRed=inputPlan[phase]['pedRed'], IsAdjustable=inputPlan[phase]['IsAdjustable'], MAX_ADJUST_RATIO=self.MAX_ADJUST_RATIO))

        CYCLE = 0
        for phase in PhaseObjectList:  # 計算週期
            CYCLE = CYCLE + phase.greenSplit + phase.pedRed + phase.allRed + phase.yellow

        signalPlan = SignalPlan.SignalPlan()  # 將SignalPlan物件實體化
        signalPlan.setAllParameters(planID=planID, phaseOrder=phaseOrder, offset=offset, cycle=CYCLE, phases=PhaseObjectList)

        #print("signalPlan = ", signalPlan)
        i.addPlan(plan=signalPlan)  # 新增這組Plan至RSU
        i.setOriginalPlan(plan=signalPlan)  # 將這組plan指定為原始時制計畫(originalPlan)

    def initialization(self, SignalPlanDict, planParameters):

        # 初始化: 新增RSU
        rsu1 = RSU.BusRSU(ID='RSU1', location=[0, 0], VANET_detection_range=0)
        # 設定各RSU的時制
        self.RSUs.update({'rsu1': rsu1})
        #print(self.RSUs['rsu1'].RSU_ID)
        #print(self.RSUs['rsu1'].location)

        Plan = []
        phaseOrder = planParameters['phaseOrder']
        offset = planParameters['offset']

        for phase in SignalPlanDict:

            greenSplit = phase['Green'] + phase['PedGreenFlash']

            Phase = {'startTime': 0, 'phaseID': phase['PhaseID'], 'greenSplit': greenSplit,
                     'green': phase['Green'], 'pedFlash': phase['PedGreenFlash'], 'yellow': phase['Yellow'],
                     'allRed': phase['AllRed'], 'pedRed': phase['PedRed'], 'Gmin': phase['Gmin'], 'Gmax': phase['Gmax'],
                     'IsAdjustable': phase['IsAdjustable']}

            Plan.append(Phase)

        self.setPhaseObject(i=self.RSUs['rsu1'], inputPlan=Plan, planID=0, phaseOrder=phaseOrder, offset=offset)

    # 計算路口通過機率
    def calPassProb(self, dist, arrivalTime, phaseTimeSplit, greenTag):  # 傳入路口RSU物件

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

    def Algorithm2_1(self, RSU, truncate_red_light_to_min, appliedPlanNum, prioritizedPhase, currentPhase, pts, greenTag, a, b, remainingTime, numOfCycleToProcess, phaseEXTandTRC_result):
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

        def adjustPhaseDuration(a, b, numOfCycleToProcess, greenTag):

            nonPP_adjAmount = a
            PP_adjAmount = b

            # step3. 調整phaseTimeSplit
            if (numOfCycleToProcess == 1):

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
                    if (b <= 0):

                        origin_pts = copy.deepcopy(pts)  # 複製當下的pts到origin pts
                        # try:  # cycle 0, prioritized Phase adj
                        #     divisionResult = math.ceil(PP_adjAmount * abs(cycle0_PP_TruncationAmount) / (abs(cycle0_PP_TruncationAmount) + abs(cycle1_PP_TruncationAmount)))
                        # except ZeroDivisionError:
                        #     divisionResult = 0
                        # pts[1] = pts[1] + divisionResult
                        pts[1] = pts[1] + phaseEXTandTRC_result['cycle0_PP_TruncationAmount']
                        updatePhaseTimeSplit(origin_pts=origin_pts)

                        origin_pts = copy.deepcopy(pts)  # 複製當下的pts到origin pts
                        # try:  # cycle 1, prioritized Phase adj
                        #     divisionResult = math.ceil(PP_adjAmount * abs(cycle1_PP_TruncationAmount) / (abs(cycle0_PP_TruncationAmount) + abs(cycle1_PP_TruncationAmount)))
                        # except ZeroDivisionError:
                        #     divisionResult = 0

                        #pts[3] = pts[3] + divisionResult
                        pts[3] = pts[3] + phaseEXTandTRC_result['cycle1_PP_TruncationAmount']
                        updatePhaseTimeSplit(origin_pts=origin_pts)

                    else:
                        origin_pts = copy.deepcopy(pts)  # 複製當下的pts到origin pts
                        # try:
                        #     divisionResult = math.ceil(PP_adjAmount * abs(cycle0_PP_ExtentAmount) / (abs(cycle0_PP_ExtentAmount) + abs(cycle1_PP_ExtentAmount)))  # cycle 0, prioritized Phase adj
                        # except ZeroDivisionError:
                        #     divisionResult = 0
                        # pts[1] = pts[1] + divisionResult
                        pts[1] = pts[1] + phaseEXTandTRC_result['cycle0_PP_ExtentAmount']
                        updatePhaseTimeSplit(origin_pts=origin_pts)

                        origin_pts = copy.deepcopy(pts)  # 複製當下的pts到origin pts
                        # try:
                        #     divisionResult = math.ceil(PP_adjAmount * abs(cycle1_PP_ExtentAmount) / (abs(cycle0_PP_ExtentAmount) + abs(cycle1_PP_ExtentAmount)))  # cycle 1, prioritized Phase adj
                        # except ZeroDivisionError:
                        #     divisionResult = 0
                        # pts[3] = pts[3] + divisionResult
                        pts[3] = pts[3] + phaseEXTandTRC_result['cycle1_PP_ExtentAmount']
                        updatePhaseTimeSplit(origin_pts=origin_pts)

                    if (a <= 0):
                        origin_pts = copy.deepcopy(pts)  # 複製當下的pts到origin pts
                        # try:
                        #     divisionResult = math.ceil(nonPP_adjAmount * abs(cycle0_nonPP_TruncationAmount) / (abs(cycle0_nonPP_TruncationAmount) + abs(cycle1_nonPP_TruncationAmount)))  # cycle 0, prioritized Phase adj
                        # except ZeroDivisionError:
                        #     divisionResult = 0
                        # pts[2] = pts[2] + divisionResult
                        pts[2] = pts[2] + phaseEXTandTRC_result['cycle0_nonPP_TruncationAmount']
                        updatePhaseTimeSplit(origin_pts=origin_pts)

                        origin_pts = copy.deepcopy(pts)  # 複製當下的pts到origin pts
                        # try:
                        #     divisionResult = math.ceil(nonPP_adjAmount * abs(cycle1_nonPP_TruncationAmount) / (abs(cycle0_nonPP_TruncationAmount) + abs(cycle1_nonPP_TruncationAmount)))  # cycle 1, prioritized Phase adj
                        # except ZeroDivisionError:
                        #     divisionResult = 0
                        # pts[4] = pts[4] + divisionResult
                        pts[4] = pts[4] + phaseEXTandTRC_result['cycle1_nonPP_TruncationAmount']
                        updatePhaseTimeSplit(origin_pts=origin_pts)

                    else:
                        origin_pts = copy.deepcopy(pts)  # 複製當下的pts到origin pts
                        # try:
                        #     divisionResult = math.ceil(nonPP_adjAmount * abs(cycle0_nonPP_ExtentAmount) / (abs(cycle0_nonPP_ExtentAmount) + abs(cycle1_nonPP_ExtentAmount)))  # cycle 0, prioritized Phase adj
                        # except ZeroDivisionError:
                        #     divisionResult = 0
                        # pts[2] = pts[2] + divisionResult
                        pts[2] = pts[2] + phaseEXTandTRC_result['cycle0_nonPP_ExtentAmount']
                        updatePhaseTimeSplit(origin_pts=origin_pts)

                        origin_pts = copy.deepcopy(pts)  # 複製當下的pts到origin pts
                        # try:
                        #     divisionResult = math.ceil(nonPP_adjAmount * abs(cycle1_nonPP_ExtentAmount) / (abs(cycle0_nonPP_ExtentAmount) + abs(cycle1_nonPP_ExtentAmount)))  # cycle 1, prioritized Phase adj
                        # except ZeroDivisionError:
                        #     divisionResult = 0
                        # pts[4] = pts[4] + divisionResult
                        pts[4] = pts[4] + phaseEXTandTRC_result['cycle1_nonPP_ExtentAmount']
                        updatePhaseTimeSplit(origin_pts=origin_pts)

                 elif (greenTag == 1):

                    if (a <= 0):
                        origin_pts = copy.deepcopy(pts)  # 複製當下的pts到origin pts
                        # try:
                        #     divisionResult = int(nonPP_adjAmount * abs(cycle0_nonPP_TruncationAmount) / (
                        #                 abs(cycle0_nonPP_TruncationAmount) + abs(cycle1_nonPP_TruncationAmount)))  # cycle 0, non-prioritized Phase adj
                        # except ZeroDivisionError:
                        #     divisionResult = 0
                        # pts[1] = pts[1] + divisionResult
                        pts[1] = pts[1] + phaseEXTandTRC_result['cycle0_nonPP_TruncationAmount']
                        updatePhaseTimeSplit(origin_pts=origin_pts)

                        origin_pts = copy.deepcopy(pts)  # 複製當下的pts到origin pts
                        # try:
                        #     divisionResult = int(nonPP_adjAmount * abs(cycle1_nonPP_TruncationAmount) / (abs(cycle0_nonPP_TruncationAmount) + abs(cycle1_nonPP_TruncationAmount)))  # cycle 0, non-prioritized Phase adj
                        # except ZeroDivisionError:
                        #     divisionResult = 0
                        # pts[3] = pts[3] + divisionResult
                        pts[3] = pts[3] + phaseEXTandTRC_result['cycle1_nonPP_TruncationAmount']
                        updatePhaseTimeSplit(origin_pts=origin_pts)

                    else:

                        origin_pts = copy.deepcopy(pts)  # 複製當下的pts到origin pts
                        # try:
                        #     divisionResult = int(nonPP_adjAmount * abs(cycle0_nonPP_ExtentAmount) / (abs(cycle0_nonPP_ExtentAmount) + abs(cycle1_nonPP_ExtentAmount)))
                        # except ZeroDivisionError:
                        #     divisionResult = 0
                        # pts[1] = pts[1] + divisionResult
                        pts[1] = pts[1] + phaseEXTandTRC_result['cycle0_nonPP_ExtentAmount']
                        updatePhaseTimeSplit(origin_pts=origin_pts)

                        origin_pts = copy.deepcopy(pts)  # 複製當下的pts到origin pts
                        # try:
                        #     divisionResult = int(nonPP_adjAmount * abs(cycle1_nonPP_ExtentAmount) / (abs(cycle0_nonPP_ExtentAmount) + abs(cycle1_nonPP_ExtentAmount)))
                        # except ZeroDivisionError:
                        #     divisionResult = 0
                        # pts[3] = pts[3] + divisionResult
                        pts[3] = pts[3] + phaseEXTandTRC_result['cycle1_nonPP_ExtentAmount']
                        updatePhaseTimeSplit(origin_pts=origin_pts)

                    if (b <= 0):
                        origin_pts = copy.deepcopy(pts)  # 複製當下的pts到origin pts
                        # try:
                        #     divisionResult = int(PP_adjAmount * abs(cycle1_PP_TruncationAmount) / (abs(cycle0_PP_TruncationAmount) + abs(cycle1_PP_TruncationAmount)))
                        # except ZeroDivisionError:
                        #     divisionResult = 0
                        # pts[2] = pts[2] + divisionResult
                        pts[2] = pts[2] + phaseEXTandTRC_result['cycle1_PP_TruncationAmount']
                        updatePhaseTimeSplit(origin_pts=origin_pts)

                    else:  # b > 0
                        origin_pts = copy.deepcopy(pts)  # 複製當下的pts到origin pts
                        # try:
                        #     divisionResult = int(PP_adjAmount * abs(cycle1_PP_ExtentAmount) / (abs(cycle0_PP_TruncationAmount) + abs(cycle1_PP_TruncationAmount)))
                        # except ZeroDivisionError:
                        #     divisionResult = 0
                        # pts[2] = pts[2] + divisionResult
                        pts[2] = pts[2] + phaseEXTandTRC_result['cycle1_PP_ExtentAmount']
                        updatePhaseTimeSplit(origin_pts=origin_pts)

                 else:
                    print("green tag error, gt = ", greenTag)
                    print(1 / 0)


            return pts

        # Step 1. 判斷是否為切斷紅燈至最短方案:
        if (truncate_red_light_to_min == False):
            pts_Result = adjustPhaseDuration(a=a, b=b,
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

                else:
                    print(1/0)

            elif (greenTag == 1):  #目標: 將cycle 0的紅燈切斷至最短 (盡快提前cycle 0的綠燈)

                if (currentPhase == RSU.plan[appliedPlanNum].phases[-1].phaseID and prioritizedPhase == RSU.plan[appliedPlanNum].phases[0].phaseID): # 特殊狀況
                    phase = RSU.plan[appliedPlanNum].phases[-1]
                    if (phase.IsAdjustable and phase.IsInUncontrollableStep == False):
                        # 條件: 若phase的行閃>0 -> 則GminLimit=0不受限
                        if phase.pedFlash > 0:
                            GminLimit = 0
                        else:
                            #GminLimit = phase.Gmin
                            GminLimit = 0

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
                                #GminLimit = phase.Gmin
                                GminLimit = 0

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

    def makeControlResultList(self, sp, arrivalTime, dist, cp, rt, rt_before_step2, pp, RSU, fF, originPTS, finalPTS, greenTag, numOfCycleToProcess):
        # 建立各時相調整量
        phaseAdjAmountDict = {'Cycle0': {}, 'Cycle1': {}}

        #新增紀錄各分相的內容
        for phaseID in range(0, 8, 1): #0~8 phase
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
                                    #GminLimit = phase.Gmin
                                    GminLimit = 0

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
                                #GminLimit = phase.Gmin
                                GminLimit = 0

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
                                        #GminLimit = phase.Gmin
                                        GminLimit = 0

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

        arrTime = int(dist / self.SPEED)
        resultList = [arrTime, cp + 1, rt, pp + 1]

        for cycle in ['Cycle0', 'Cycle1']:
            for phaseID in range(0, 8, 1):
                resultList.append(phaseAdjAmountDict[cycle][phaseID])

        return resultList

    def calPhase_MAX_EXTENT_and_TRUNCATE(self, RSU, cycleAmount, currentPhase, prioritizedPhase, remainingTime, appliedPlanNum):

        # a -> non-prioritized phase (nonPP) / b -> prioritized phase (PP)
        cycle0_nonPP_ExtentAmount = 0
        cycle0_nonPP_TruncationAmount = 0
        cycle1_nonPP_ExtentAmount = 0
        cycle1_nonPP_TruncationAmount = 0

        cycle0_PP_ExtentAmount = 0
        cycle0_PP_TruncationAmount = 0
        cycle1_PP_ExtentAmount = 0
        cycle1_PP_TruncationAmount = 0

        # 延長
        for phase in RSU.plan[appliedPlanNum].phases[currentPhase:]:  # 從currentPhase開始取出時相物件

            if (phase.IsAdjustable and phase.IsInUncontrollableStep == False):  # 先確認該phase是可以調整的

                if (phase.phaseID == prioritizedPhase):  # 遇到prioritizedPhase特別挑出
                    cycle0_PP_ExtentAmount = cycle0_PP_ExtentAmount + phase.EXTENT_LIMIT
                else:  # phaseID != prioritizedPhase
                    cycle0_nonPP_ExtentAmount = cycle0_nonPP_ExtentAmount + phase.EXTENT_LIMIT

        # 切斷
        for phase in RSU.plan[appliedPlanNum].phases[currentPhase:prioritizedPhase]:  # 從currentPhase開始取出時相物件
            # 遇到currentPhase特別挑出: 避免違反Gmin條件，另需區分greentTag = 0 或 greenTag = 1 兩種狀況
            # 條件: 若phase的行閃>0 -> 則GminLimit=0不受限

            if (phase.IsAdjustable and phase.IsInUncontrollableStep == False):  # 先確認該phase是可以調整的

                if phase.pedFlash > 0:
                    GminLimit = 0
                else:
                    # GminLimit = phase.Gmin
                    GminLimit = 0

                if (phase.phaseID == currentPhase and currentPhase == prioritizedPhase):

                    if (remainingTime >= GminLimit + abs(phase.TRUNCATION_LIMIT)):  # 1 剩餘秒數 >= 最短綠 + 時相最大允許切斷量
                        cycle0_PP_TruncationAmount = phase.TRUNCATION_LIMIT
                    elif ((GminLimit < remainingTime) and (remainingTime < GminLimit + abs(
                            phase.TRUNCATION_LIMIT))):  # 2 最短綠 < 剩餘秒數 < 最短綠 + 時相最大允許切斷量
                        cycle0_PP_TruncationAmount = GminLimit - remainingTime
                    else:  # 3 remainingTime <= Gmin  剩餘秒數<最短綠 -> 不可切斷
                        cycle0_PP_TruncationAmount = 0

                elif (phase.phaseID == currentPhase and currentPhase != prioritizedPhase):
                    if (remainingTime >= GminLimit + abs(phase.TRUNCATION_LIMIT)):  # 1 剩餘秒數 >= 最短綠 + 時相最大允許切斷量
                        cycle0_nonPP_TruncationAmount = phase.TRUNCATION_LIMIT
                    elif ((GminLimit < remainingTime) and (remainingTime < GminLimit + abs(
                            phase.TRUNCATION_LIMIT))):  # 2 最短綠 < 剩餘秒數 < 最短綠 + 時相最大允許切斷量
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

            for phase in RSU.plan[appliedPlanNum].phases[:prioritizedPhase]:

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

        resultDictionary = {'cycle0_nonPP_TruncationAmount': cycle0_nonPP_TruncationAmount, 'cycle0_PP_TruncationAmount': cycle0_PP_TruncationAmount,
                            'cycle0_nonPP_ExtentAmount': cycle0_nonPP_ExtentAmount, 'cycle0_PP_ExtentAmount': cycle0_PP_ExtentAmount,
                            'cycle1_nonPP_TruncationAmount': cycle1_nonPP_TruncationAmount, 'cycle1_PP_TruncationAmount': cycle1_PP_TruncationAmount,
                            'cycle1_nonPP_ExtentAmount': cycle1_nonPP_ExtentAmount, 'cycle1_PP_ExtentAmount': cycle1_PP_ExtentAmount,
                            'max_nonPP_ExtentAmount': max_nonPP_ExtentAmount, 'max_nonPP_TruncationAmount':max_nonPP_TruncationAmount,
                            'max_PP_ExtentAmount':max_PP_ExtentAmount, 'max_PP_TruncationAmount':max_PP_TruncationAmount}

        return resultDictionary


    def main(self, arrivalTime, cp, pp, rt):

        dist = int(self.SPEED * arrivalTime)

        M = 9999999

        newPassProb = 0
        nonPrioritizedPhase_Adjustment = 0
        PrioritizedPhase_Adjustment = 0
        newPhaseTimeSplit = 0

        success_count = 0
        fail_count = 0
        #開始運算
        for sp in [0]:

            # 特別說明：(1) 控制器的rt指 剩餘綠燈 + 行閃 + 行紅 + 黃燈 + 全紅
            #           (2) 本程式rt指 剩餘綠燈秒數
            # 綜合以上兩者需進行判斷轉換
            # rt_for_passProb = 用於計算通過機率的rt
            # rt_for_calStrategy = 用於計算優先策略的rt

            rt_for_resume = rt  # 備份rt

            if ((cp not in range(0, len(self.RSUs['rsu1'].plan[sp].phases), 1)) or (pp not in range(0, len(self.RSUs['rsu1'].plan[sp].phases), 1))):
                adjResult = self.makeControlResultList(sp=sp, arrivalTime=arrivalTime, dist=dist, cp=cp, rt=rt, rt_before_step2=rt, pp=pp, RSU=self.RSUs['rsu1'], fF=True,
                               originPTS=[], finalPTS=[], greenTag=0, numOfCycleToProcess=1)
                print("adjResult = ", adjResult)

            else:

                pedFlash = self.RSUs['rsu1'].plan[sp].phases[cp].pedFlash
                pedRed = self.RSUs['rsu1'].plan[sp].phases[cp].pedRed
                yellow = self.RSUs['rsu1'].plan[sp].phases[cp].yellow
                allRed = self.RSUs['rsu1'].plan[sp].phases[cp].allRed

                redRemainTime = pedFlash + pedRed + yellow + allRed

                if (redRemainTime < rt):  # 若rt > redRemainTime 則表示步階1還有秒數剩餘，仍然可以調整!
                    print("rt = ", rt, " > redRemainTime = ", redRemainTime, " 步階1還有秒數剩餘，仍然可以調整!")
                    rt_for_passProb = rt - (allRed + yellow + pedRed)  # 用於計算通過機率
                    rt_for_calStrategy = rt - redRemainTime  # 用於計算策略

                    self.RSUs['rsu1'].plan[sp].phases[cp].setIsInUncontrollableStep(False)

                elif ((allRed + yellow + pedRed) < rt and rt <= redRemainTime):  # 進入行閃階段，步階1無法調整!
                    print("rt = ", rt, " redRemainTime = ", redRemainTime, " 步階1無法調整!")
                    rt_for_passProb = rt - (allRed + yellow + pedRed)
                    rt_for_calStrategy = 0

                    self.RSUs['rsu1'].plan[sp].phases[cp].setIsInUncontrollableStep(True)  # 步階1無法調整 -> 將IsInUncontrollableStep設定True -> 使計算調整秒數時不去動他

                else:
                    print("rt = ", rt, " redRemainTime = ", redRemainTime, " 步階1無法調整!")
                    rt_for_passProb = 0  # 若rt <= redRemainTime 則表示已進入紅燈時間 -> 約略等於 rt=0
                    rt_for_calStrategy = 0
                    self.RSUs['rsu1'].plan[sp].phases[cp].setIsInUncontrollableStep(True)  # 步階1無法調整 -> 將IsInUncontrollableStep設定True -> 使計算調整秒數時不去動他


                failFlag = False
                print("*******************************************************************")
                print("sp = ", sp, "dist = ", dist, "ariivalTime = ", arrivalTime, "cp = ", cp, "rt = ", rt,
                      "rt_for_passProb = ", rt_for_passProb, "rt_for_calStrategy = ", rt_for_calStrategy,
                      "pp = ", pp)


                result = self.RSUs['rsu1'].calPhaseTimeSplit_NEW(appliedPlanNum=sp, targetPhase=pp, currentPhase=cp,
                                                            remainingTime_gt0=rt_for_passProb, remainingTime_gt1=rt)
                phaseTimeSplit = result[0]
                greentag = result[1]
                print("phaseTimeSplit = ", phaseTimeSplit)
                print("greenTag = ", greentag)

                passProb = self.calPassProb(dist=dist, arrivalTime=arrivalTime, phaseTimeSplit=phaseTimeSplit, greenTag=greentag)

                # Step 1. 先把phaseTimeSplit備份一份
                original_pts = copy.deepcopy(phaseTimeSplit)
                print("origin phase time split = ", original_pts)

                if (passProb < self.Thr):    # 通過機率小於門檻值

                    numOfCycleToProcess = self.RSUs['rsu1'].cal_NumOfCycleToProcess_NEW(dist=dist, speed=0, arrivalTime=arrivalTime, cp=cp, rt=rt_for_passProb, sp=sp)

                    # 20210520

                    if (numOfCycleToProcess > 1):
                        print("rrrr")
                    result = self.calPhase_MAX_EXTENT_and_TRUNCATE(RSU=self.RSUs['rsu1'], cycleAmount=numOfCycleToProcess, appliedPlanNum=sp,
                                                          currentPhase=cp, remainingTime=rt_for_calStrategy, prioritizedPhase=pp)

                    print("xxx")
                    # NON_PRIORITIZED_PHASE_ADJ_LIMIT = round(sum(phase.green for phase in self.RSUs['rsu1'].plan[sp].phases if phase.phaseID != pp) * self.MAX_ADJUST_RATIO)
                    # PRIORITIZED_PHASE_ADJ_LIMIT = round(self.RSUs['rsu1'].plan[sp].phases[pp].green * self.MAX_ADJUST_RATIO)

                    totalAdjustment = M

                    if (numOfCycleToProcess < 2):
                        non_prioritized_phase_adj_range = range(result['max_nonPP_TruncationAmount'], 1) # 1: in order to include 0
                        if (result['max_PP_ExtentAmount'] == 0):
                            result['max_PP_ExtentAmount'] = result['max_PP_ExtentAmount'] + 1
                        prioritized_phase_adj_range = range(0, result['max_PP_ExtentAmount'])  # -1: in order to include 0
                    else:
                        if (result['max_nonPP_ExtentAmount'] == 0): result['max_nonPP_ExtentAmount'] = result['max_nonPP_ExtentAmount'] + 1
                        if (result['max_PP_ExtentAmount'] == 0): result['max_PP_ExtentAmount'] = result['max_PP_ExtentAmount'] + 1

                        non_prioritized_phase_adj_range = range(result['max_nonPP_TruncationAmount'], result['max_nonPP_ExtentAmount'])
                        prioritized_phase_adj_range = range(result['max_PP_TruncationAmount'], result['max_PP_ExtentAmount'])

                    # a-> 非公車優先時相調整量  b-> 公車優先時相調整量
                    for a in non_prioritized_phase_adj_range:
                        for b in prioritized_phase_adj_range:

                            phaseTimeSplit_result = self.Algorithm2_1(RSU=self.RSUs['rsu1'], pts=phaseTimeSplit, greenTag=greentag, a=a, b=b,
                                                                      numOfCycleToProcess=numOfCycleToProcess, appliedPlanNum=sp, prioritizedPhase=pp, currentPhase=cp,
                                                                      remainingTime=rt_for_calStrategy, truncate_red_light_to_min=False,
                                                                      phaseEXTandTRC_result=result)

                            # exception test-> 檢查回傳值是否有負值:
                            for num in phaseTimeSplit:
                                if num < 0:
                                    #print("error")
                                    print(1/0)  #丟出exception

                            phaseTimeSplit = copy.deepcopy(original_pts)  # phaseTimeSplit回復到原始時制
                            tempPassProb = self.calPassProb(dist=dist, arrivalTime=arrivalTime, phaseTimeSplit=phaseTimeSplit_result, greenTag=greentag)

                            if (tempPassProb >= self.Thr):
                                if (abs(a) + abs(b)) < totalAdjustment:
                                    totalAdjustment = abs(a) + abs(b)
                                    nonPrioritizedPhase_Adjustment = a
                                    PrioritizedPhase_Adjustment = b
                                    newPassProb = tempPassProb
                                    newPhaseTimeSplit = phaseTimeSplit_result


                    if totalAdjustment != M:
                        print("========== 有找到優先控制方案！ ===========")
                        print("sp = ", sp, "dist = ", dist, "arrivalTime = ", arrivalTime, "cp = ", cp,
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
                        phaseTimeSplit_result = self.Algorithm2_1(RSU=self.RSUs['rsu1'], truncate_red_light_to_min=True, pts=phaseTimeSplit,
                                                             greenTag=greentag, a=0, b=0, numOfCycleToProcess=numOfCycleToProcess,
                                                             appliedPlanNum=sp, prioritizedPhase=pp, currentPhase=cp, remainingTime=rt_for_calStrategy, phaseEXTandTRC_result=0)
                        phaseTimeSplit = copy.deepcopy(original_pts)  # phaseTimeSplit回復到原始時制
                        if (phaseTimeSplit_result != False):
                            finalPassProb = self.calPassProb(dist=dist, arrivalTime=arrivalTime, phaseTimeSplit=phaseTimeSplit_result, greenTag=greentag)
                            print("========== 切斷紅燈至最短！ ==============")
                            print("sp = ", sp, "dist = ", dist, "arrivalTime = ", arrivalTime, "cp = ", cp,
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
                            failFlag = True
                            finalPhaseTimeSplit = 0

                else:  # 通過機率足夠，不用更動號誌
                    print("========== 通過機率足夠！ 不用更動號誌 ==============")
                    print("sp = ", sp, "dist = ", dist, "arrivalTime = ", arrivalTime, "cp = ", cp,
                          "rt_for_passProb = ", rt_for_passProb, "rt_for_calStrategy = ", rt_for_calStrategy,
                          "pp = ", pp, "greenTag = ", greentag)
                    print("originalPhaseTimeSplit = ", phaseTimeSplit)
                    print("原始通過機率 = ", round(passProb, 4))
                    finalPhaseTimeSplit = phaseTimeSplit
                    numOfCycleToProcess = 0


                adjResult = self.makeControlResultList(sp=sp, arrivalTime=arrivalTime, dist=dist, cp=cp, rt=rt, rt_before_step2=rt_for_calStrategy, pp=pp, RSU=self.RSUs['rsu1'],
                               fF=failFlag, originPTS=original_pts, finalPTS=finalPhaseTimeSplit, greenTag=greentag,
                               numOfCycleToProcess=numOfCycleToProcess)

            finalAdjustResult = adjResult

            return finalAdjustResult

    def run(self, arrivalTime, cp, pp, rt):

        self.initialization(self.SignalPlan, self.planParameters)  # 初始化號誌物件

        cp = cp - 1  #Unify the units of phase number to start from 0
        pp = pp - 1

        finalAdjustResult = self.main(arrivalTime=arrivalTime, cp=cp, pp=pp, rt=rt)
        return finalAdjustResult



