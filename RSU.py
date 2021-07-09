import math
import copy
from scipy.stats import norm
#from thesis import RSUObject
import numpy as np

phaseStrDict = {0: "J1", 1: "J2", 2: "J3", 3: "J4",4: "J5", 5: "J6", 6: "J7", 7: "J8"}
phaseStrDict_rev = {"J1": 0, "J2":1, "J3":2, "J4":3, "J5":4, "J6":5, "J7":6, "J8":7}
phaseLogicPairNum = {0: 0, 1: 0, 2: 3, 3: 3, 4: 6, 5: 6, 6: 9, 7: 9}
#


# free flow speed
Vf = 12
# # 乘載人數
# OCC_BUS = 30
# OCC_AUTO = 1.5

# 號誌參數
M = 9999999

#PASS_PROB_THRESHOLD = 0.8

#公車參數
#BUS_ACTIVATION_SPEED_THRESHOLD = 0
MAX_NUMBER_OF_CYCLE_PROCESSED = 2 # 最多處理幾個cycle


class simTime_less_accCycle_error(Exception):
    def __init__(self,msg):
        self.message=msg


class BusRSU():
    flag = True

    def __init__(self, ID, location, VANET_detection_range):
        self.RSU_ID = ID
        self.location = location
        self.VANET_detection_range = VANET_detection_range

        self.timeAccumulated = 0  #本rsu總累積時間長度，用於計算相對抵達時間
        self.plan = []  # 時制計畫 (依照週期順序排列)
        self.modifiedPlan = []  # 修改後的時制計畫(可能不只一組)
        self.originalPlan = 0  # 原定時制時制計畫 (只有一組)
        self.ServiceCode = 0  # 服務代號
        self.HostOBU = 0
        self.numberOfCompetePhase = 0  # 競相時相總數量
        self.numberOfSignalCycleProcessed = 1  # 預計要處理的週期數
        self.avgQueueLength = {'J1': 0}  # 各時相平均Queue長度

    # 新增時制計畫
    def addPlan(self, plan):
        self.plan.append(plan)
    # 刪除時制計畫
    def removePlan(self, planID):
        return 0

    # 設定原始時制計畫
    def setOriginalPlan(self, plan):
        self.originalPlan = plan

    # 回復到原始時制計畫
    def resumePlan(self):
        self.plan = copy.deepcopy(self.originalPlan)

    # 計算並設定競相數量
    def set_numberOfCompetePhase(self):

        # 競相時相數量 = 原預設時制數量 - 1 (OBU的目標時相targerPhase)
        if (len(self.originalPlan > 0)):
            self.numberOfCompetePhase = len(self.originalPlan - 1)
        else:
            self.numberOfCompetePhase = 0
            print("例外錯誤: 沒有新增plan (len of plan = 0)")

    # 取得目前運作時相狀態
    # def getCurrentPlanState(self):
    #     return self.RSU_ID, currentPlan, currentPhaseID, remainingSeconds

    # 計算時間分割點
    def calPhaseTimeSplit(self, targetPhase):

        # 引數說明：
        # targetPhase: 指定要計算的phase編號(str)

        phaseTimeSplit = []  # 紀錄時相切割時間點

        if targetPhase in ['J1']:  # 時相編號為1是週期起頭時相
            IsHeadPhase = True
            # 起頭時相 phaseSplit = [(0) 紅燈起始, (1) 紅燈結束, (2)紅燈起始,..., (n)紅燈結束]

            #### 計算週期K ####
            # Expect: plan[0][targetPhase].startTime = 0
            targetPhaseEndTime = self.plan[0].phases[targetPhase].startTime + self.plan[0].phases[targetPhase].greenSplit
            phaseTimeSplit.append(targetPhaseEndTime)  # 加入 時相結束時間 = (0) 紅燈起始

            #### 計算週期K+1 ####
            targetPhaseStartTime = self.plan[1].phases[targetPhase].startTime  # 加入 時相起始時間 = (1) 紅燈結束
            phaseTimeSplit.append(targetPhaseStartTime)
            phaseTimeSplit.append(
                targetPhaseStartTime + self.plan[1].phases[targetPhase].greenSplit)  # 加入 時相結束時間 = (2) 紅燈起始

            #### 計算週期K+n ####
            cycle = self.plan[2].cycle

            for num in range(2, 5):  # 這裡修改可設定一次產生幾個週期(k+2 k+3...)後的時間
                if (num == 2):
                    phaseTimeSplit.append(self.plan[2].phases[targetPhase].startTime)  # 時相在週期k+2的起始時間 = (1) 紅燈結束
                    startPoint = self.plan[2].phases[targetPhase].startTime
                phaseTimeSplit.append(
                    startPoint + self.plan[2].phases[targetPhase].greenSplit)  # 時相在週期k+n的結束時間 = (2) 紅燈起始
                startPoint = startPoint + cycle  # 再加一個週期 -> 時相在k+n的起始時間 = (n) 紅燈結束
                phaseTimeSplit.append(startPoint)


        elif targetPhase in ['J2', 'J3', 'J4', 'J6', 'J7', 'J8']:  # 其他時相編號 (非起頭時相)
            IsHeadPhase = False
            numType_Of_targetPhase = phaseStrDict_rev[targetPhase]  # 字串轉換為數字型態
            phaseTimeSplit.append(0)  # 在最開始處新增0 (表示由0秒處紅燈起始)
            # 非起頭時相 phaseSplit = [(0) 0, (1) 紅燈結束, (2) 紅燈起始, (3)紅燈結束, (4)紅燈起始, ... , (n)紅燈結束]
            #### 計算週期K ####
            startPoint = self.plan[0].phases[numType_Of_targetPhase].startTime  # targetPhase的起始時間 ( = (1) 紅燈結束時間)
            phaseTimeSplit.append(startPoint)
            phaseTimeSplit.append(
                startPoint + self.plan[0].phases[numType_Of_targetPhase].green)  # targetPhase結束時間 ( = (2) 紅燈起始時間)

            #### 計算週期K+1 ####
            startPoint = self.plan[1].phases[numType_Of_targetPhase].startTime  # targetPhase 起始時間 = (3) 紅燈結束時間
            phaseTimeSplit.append(startPoint)
            phaseTimeSplit.append(
                startPoint + self.plan[1].phases[numType_Of_targetPhase].green)  # targetPhase結束時間 ( = (4) 紅燈起始時間)

            #### 計算週期K+n ####
            # 計算k+1週期長度
            cycle = self.plan[2].cycle
            # cycle = (plan[1]['J4'].startTime + plan[1]['J4'].green + plan[1]['J4'].yellow + plan[1]['J4'].allRed) - (plan[1]['J1'].startTime)

            for num in range(2, 5):  # 這裡修改可設定一次產生幾個週期( k+2 k+3...)後的時間
                if (num == 2):
                    startPoint = self.plan[2].phases[
                        numType_Of_targetPhase].startTime  # k+1週期的targetPhase起始時間 = (3) 紅燈結束
                    phaseTimeSplit.append(startPoint)
                phaseTimeSplit.append(startPoint + self.plan[2].phases[
                    numType_Of_targetPhase].green)  # k+1週期的targetPhase結束時間 = (4) 紅燈起始
                startPoint = startPoint + cycle  # k+2週期targetPhase的起始時間 = (n) 紅燈結束
                phaseTimeSplit.append(startPoint)
        else:  # 例外錯誤
            print("例外錯誤:　targetPhase = ", targetPhase)
            print(1 / 0)

        return phaseTimeSplit, IsHeadPhase  # 回傳 [0] 時間分割點 [1] 是否為起頭時相
        # return phaseTimeSplit # 回傳時間分割點

    # 計算時間分割點(新)
    def calPhaseTimeSplit_NEW(self, appliedPlanNum, targetPhase, currentPhase, remainingTime_gt0, remainingTime_gt1):

        phaseTimeSplit = []  # 紀錄時相切割時間點

        if (currentPhase == targetPhase) :  # 若當下運作的時相就是要計算的時相(greentag=0)

            greenTag = 0  # [(0)綠燈 , (1) 綠燈結束, (2) 綠燈開始, (3)綠燈結束,..., (n)綠燈開始, (n+1)綠燈結束 ]
            phaseTimeSplit.append(0)  # 加入(0) 起頭，此時到(1)之時間皆為綠燈時間

            #### 計算週期K ####
            currentPhaseGreenEndTime = remainingTime_gt0
            phaseTimeSplit.append(currentPhaseGreenEndTime)  # 加入 時相結束時間 = (1) 綠燈結束
            currentPhaseEndTime = remainingTime_gt0 + self.plan[appliedPlanNum].phases[currentPhase].yellow \
                                  + self.plan[appliedPlanNum].phases[currentPhase].allRed + self.plan[appliedPlanNum].phases[currentPhase].pedRed

            #### 計算週期K+1 ####
            sumOfOtherPhasesDuration = 0
            import itertools
            phasePool = itertools.cycle(self.plan[appliedPlanNum].phases)
            phasePool_startAtCurrentPhaseNext = itertools.islice(phasePool, currentPhase + 1, None) #從下一個phase開始
            for phase in phasePool_startAtCurrentPhaseNext:
                if (phase.phaseID == targetPhase):  # 到公車優先時相結束
                    break
                else:
                    sumOfOtherPhasesDuration = sumOfOtherPhasesDuration + phase.greenSplit + phase.yellow + phase.allRed + phase.pedRed


            # if (targetPhase == len(self.plan[appliedPlanNum].phases) - 1):  # 若targetphase是plan中最後一個phase
            #     for phase in self.plan[appliedPlanNum].phases[:currentPhase]:
            #         sumOfOtherPhasesDuration = sumOfOtherPhasesDuration + phase.greenSplit + phase.yellow + phase.allRed + phase.pedRed
            # else:
            #     for phase in self.plan[appliedPlanNum].phases[currentPhase+1:]:
            #         sumOfOtherPhasesDuration = sumOfOtherPhasesDuration + phase.greenSplit + phase.yellow + phase.allRed + phase.pedRed
            #                       # 綠燈結束時間 + 黃燈 + 全紅 + 其他非優先時相長度總合 = 下次綠燈開始時間
            #
            # CurrentPhaseRedReaminTime = self.plan[appliedPlanNum].phases[currentPhase].yellow + self.plan[appliedPlanNum].phases[currentPhase].allRed \
            #                             + self.plan[appliedPlanNum].phases[currentPhase].pedRed

            targetPhaseStartTime = currentPhaseEndTime + sumOfOtherPhasesDuration

            phaseTimeSplit.append(targetPhaseStartTime)  # 加入 時相起始時間 = (2) 綠燈開始
            phaseTimeSplit.append(targetPhaseStartTime + self.plan[appliedPlanNum].phases[targetPhase].greenSplit)  # 加入 時相結束時間 = (3) 綠燈結束

            #### 計算週期K+n ####
            cycle = self.plan[appliedPlanNum].cycle
            startPoint = 0
            for num in range(2, 5):  # 這裡修改可設定一次產生幾個週期(k+2 k+3...)後的時間
                startPoint = phaseTimeSplit[2] + cycle * (num-1)  # [1] 為時相綠燈開始時間點
                phaseTimeSplit.append(startPoint)  # 加入 時相開始時間 =  綠燈開始
                phaseTimeSplit.append(startPoint + self.plan[appliedPlanNum].phases[targetPhase].greenSplit)  # 加入 時相結束時間 =  綠燈結束

            #phaseTimeSplit.append(phaseTimeSplit[-2] + cycle)  # 加入 時相開始時間 = 綠燈開始

        else:  # 當下運作的時相非目標時相
            greenTag = 1  # [(0) 綠燈尚未開始(紅燈)  (1) 綠燈開始, (2) 綠燈結束, (3)綠燈開始,..., (n)綠燈結束]
            phaseTimeSplit.append(0)  # 加入(0) 起頭，此時到(1)之時間皆為紅燈時間

            # 若目標時相是當下時相的下一個
            if ((targetPhase == currentPhase + 1) or (targetPhase == 0 and currentPhase == self.plan[appliedPlanNum].phases[-1].phaseID)):

                #### 計算週期K ###
                currentPhaseEndTime = remainingTime_gt1
                phaseTimeSplit.append(currentPhaseEndTime)  # 加入 目標時相開始時間 = (0) 綠燈開始
                phaseTimeSplit.append(currentPhaseEndTime + self.plan[appliedPlanNum].phases[targetPhase].greenSplit) # 加入 目標時相結束時間 = (1) 綠燈結束
                #### 計算週期K+n ###
                cycle = self.plan[appliedPlanNum].cycle
                for num in range(2, 5):  # 這裡修改可設定一次產生幾個週期(k+2 k+3...)後的時間
                    startPoint = phaseTimeSplit[1] + cycle * (num - 1)
                    phaseTimeSplit.append(startPoint)  # 加入 時相綠燈開始時間
                    phaseTimeSplit.append(startPoint + self.plan[appliedPlanNum].phases[targetPhase].greenSplit)  # 加入 時相綠燈結束時間

            else: #目標時相和當下時相距離超過一個phase

                #### 計算週期K ###
                startPoint = remainingTime_gt1
                import itertools
                phasePool = itertools.cycle(self.plan[appliedPlanNum].phases)
                phasePool_startAtCurrentPhaseNext = itertools.islice(phasePool, currentPhase+1, None)
                for phase in phasePool_startAtCurrentPhaseNext:
                    if (phase.phaseID == targetPhase): #到公車優先時相結束
                        break
                    else:
                        startPoint = startPoint + phase.greenSplit + phase.yellow + phase.allRed + phase.pedRed
                phaseTimeSplit.append(startPoint)  # (0) 目標時相綠燈起始
                phaseTimeSplit.append(startPoint + self.plan[appliedPlanNum].phases[targetPhase].greenSplit)  # (1)目標時相綠燈結束

                #### 計算週期K+n ###
                cycle = self.plan[appliedPlanNum].cycle
                startPoint = 0
                for num in range(2, 5):  # 這裡修改可設定一次產生幾個週期(k+2 k+3...)後的時間
                    startPoint = phaseTimeSplit[1] + cycle * (num - 1)
                    phaseTimeSplit.append(startPoint)  # 加入 時相綠燈開始時間
                    phaseTimeSplit.append(
                        startPoint + self.plan[appliedPlanNum].phases[targetPhase].greenSplit)  # 加入 時相綠燈結束時間

        return phaseTimeSplit, greenTag  # 回傳 [0] 時間分割點 [1] 起頭為綠燈開始或結束



    # # 更新RSU累積週期長度
    # def updateCycleAccumulated(self):
    #     nowPhase = traci.trafficlight.getPhase('I1')
    #     nowProgramLogic = traci.trafficlight.getAllProgramLogics('I1')
    #     if (nowPhase in (11,23) and self.flag == True):
    #         #該週期已結束
    #         for phase in nowProgramLogic[0].phases:
    #             phaseDuration = phase.duration
    #             # 累計新增該週期時間
    #             self.CycleAccumulated = self.CycleAccumulated + phaseDuration
    #         self.flag = False
    #
    #         if (nowPhase == 23 and traci.trafficlight.getProgram('I1') == '1'): # switch TLS program from '1' to '0'
    #             traci.trafficlight.setProgram('I1', '0')
    #
    #     else:
    #         self.flag = True

    # 計算公車優先號誌需要處理幾個cycle
    def cal_NumOfCycleToProcess(self, OBU):

        # 取得OBU絕對抵達時間
        absoluteArrivalTime = self.calArrivalTime(OBU=OBU)[0]
        # 取得當下週期結束時間點
        cycle_k_endTimePoint = self.CycleAccumulated + self.originalPlan.cycle

        if (absoluteArrivalTime >= cycle_k_endTimePoint):
            # 跨到第二個周期 -> 需要一次處理當兩周期: 當下週期 + 下個週期
            self.numberOfSignalCycleProcessed = 2
        else:  # 沒有跨到第二個周期 -> 只處裡當下週期
            self.numberOfSignalCycleProcessed = 1

        print("self.numberOfSignalCycleProcessed = ", self.numberOfSignalCycleProcessed)

    def cal_NumOfCycleToProcess_NEW(self, dist, speed, arrivalTime, sp, cp, rt):

        if (speed > 0): #arrival time is calculated if speed were provided (i.e. speed > 0)
            arrivalTime = dist / speed

        deviation = math.ceil((2 + dist / 50) / 3)  # 標準差
        lowBound = max(0, round(arrivalTime - 3 * deviation))  # 抵達時間下界
        # 計畫從cp開始
        nextCycleStartTime = rt + self.plan[sp].phases[cp].pedRed + self.plan[sp].phases[cp].yellow + self.plan[sp].phases[cp].allRed

        for phase in self.plan[sp].phases[cp+1:]:
            nextCycleStartTime = nextCycleStartTime + phase.greenSplit + phase.pedRed +phase.yellow + phase.allRed

        if (lowBound >= nextCycleStartTime):
            # 跨兩個週期
            numOfCycleNeedProcessed = 2
        else:
            numOfCycleNeedProcessed = 1

        return numOfCycleNeedProcessed

    # 確認RSU公車優先狀態
    def Check_TSP_indicator(self):
        return 0


    def __str__(self):
        return 'RSU(ID = {0}, location = {1},  plan = {2})'\
            .format(self.RSU_ID, self.location, self.plan)





