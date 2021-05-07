import traci
import math
import thesis.PhaseObject as PhaseObject
# from thesis import OBUObject
from scipy.stats import norm

OBU_START_INDICATOR = 1  #公車車機是否啟動

phaseStrDict_rev = {"J1": 0, "J2":1, "J3":2, "J4":3, "J5":4, "J6":5, "J7":6, "J8":7}

# 路口群組編號
intersectionGroup_outbound = {"01", "02"}
intersectionGroup_inbound = {"02", "01"}

#路口群組-目標路口對應 (名稱) # outbound 順行 inbound 逆行
targetIntersections_outbound = {"G1":['C2','C6'], "G2":['C7','C8','C9']}
targetIntersections_inbound = {"G1":['C2'], "G2":['C9', 'C8', 'C7', 'C6']}

# 路口 (座標點)
intersectionPosition = {"C2": [-364.45, 50.01], "C6": [0.50,50.32], "C7": [62.33,50.37] }


class OBU():

    # ### Settings ###
    # passProbThreshold = 0.8  # 路口通過機率門檻
    # maxSpeedLimit = 15  # 約 54 km/hr
    # MaxSpeedFactor = 0.1
    # MinSpeedFactor = 0.3
    # OBU_TSP_INDICATOR = 1 # 公車優先每個路口只做一次，做完後=0
    # PLAN_C_INDICATOR = False
    # maxSpeedLimit = 15  # 約 54 km/hr

    OBU_RECOMMENDED_SPEED_INDICATOR = 1  # 駕駛建議每路口只做一次，做完後=0

    PASS_PROB_THRESHOLD = 0.8  # 路口通過機率門檻

    MAX_SPEED_FACTOR = 0.1
    MIN_SPEED_FACTOR = 0.3

    def __init__(self,ID,vehType,pos,currentSpeed,direction,hostRSU,targetPhase,occupancy,duty):
        self.OBU_ID = ID # 車輛OBU ID
        self.vehType = vehType # 車種
        self.position = pos # 公車座標位置
        self.currentSpeed = currentSpeed # 當下速度
        self.direction = direction # 公車方向 (0 = 順行 或 1 = 逆行)
        self.targetIntersections = []  # 目標路口群組
        self.targetIntersections_redTimeDelay = {} #路口群組內各路口之停等紅燈延滯時間
        self.targetIntersections_expectedArrivalTime = {} #路口群組內各路口之預期抵達時間
        self.hostRSU = hostRSU  # 前方路口
        self.targetPhase = targetPhase # 目標時相
        self.busStopState = 0 # 行車狀態 (0 = 行駛中 或 1 = 停站中)
        self.occupancy = occupancy # 乘客數
        self.duty = duty #值勤狀態 (0 = 無值勤 或 1 = 值勤中)

        #self.needOptIntersectionList = []  # 需要計算駕駛建議的路口
        #self.intersectionPassProb = {}  # 紀錄路口i的通過機率，初始值為100%
        self.recommendSpeed = 0 # 駕駛建議速度

    # 啟動駕駛建議
    def startSpeedGuidance(self, RSUs): #傳入各路口RSU物件(字典型態)
        global OBU_START_INDICATOR
        # global OBU_RECOMMENDED_SPEED_INDICATOR
        # global PLAN_C_INDICATOR
        print("OBU_START_INDICATOR = ", OBU_START_INDICATOR)
        print("OBU_RECOMMENDED_SPEED_INDICATOR = ", self.OBU_RECOMMENDED_SPEED_INDICATOR)
        print("PLAN_C_INDICATOR = ", self.PLAN_C_INDICATOR)
        if (OBU_START_INDICATOR == 1): # 公車車機是否啟動
            # RSUs = {'I1':I1(RSU物件), 'I2':I2(RSU物件), ... }
            # 0. 初始化: 將相關屬性重設
            self.needOptIntersectionList = []
            self.targetIntersectionList = []
            # 1. 找targetIntersections
            result = self.findTargetIntersections() # 沿用父類別方法
            if (result): #若回傳為true才繼續，否則不執行以下
                # 2. 計算各路口通過機率
                if (self.OBU_RECOMMENDED_SPEED_INDICATOR == 1 and self.currentSpeed > 10):
                    for i in self.targetIntersectionList:
                        passProbResult = self.calPassProb(RSUs[i]) # 呼叫計算OBU通過機率
                        if (passProbResult != False):  # False = 公車已經停止(除0速度錯誤)，不需要計算駕駛建議
                            self.intersectionPassProb.update({i:passProbResult}) # 更新intersectionPassProb list
                            self.needOptIntersectionList.append(i) # 將路口加入需要計算路口列表中

                            if (passProbResult <= self.passProbThreshold):  # 若通過機率小於門檻值
                                print("路口[ %s ]通過機率 = %f < = 目標機率 %f，需要計算駕駛建議速度" % (i, self.intersectionPassProb[i], self.passProbThreshold))
                                euslt = self.calOptimalSpeed(RSUs)  # 計算駕駛建議
                                break
                            else: # 若通過機率大於門檻值，不用計算建議速度
                                # Plan A
                                print("Plan A: 路口[ %s ]通過機率 = %f > 目標機率 %f，建議速度 = 目前速度" % (i, self.intersectionPassProb[i], self.passProbThreshold))
                                traci.vehicle.setSpeed(self.OBU_ID, -1)
                                return True
                        else:  # if passProbResult == False
                            # 公車已停止
                            # print("passProb = ", passProb)
                            return False

                    # 檢查是否有計算出新的建議速度
                    if (self.recommendSpeed != 0):
                        # Plan B
                        # recommendSpeed != 0 表示窮舉中有速度之通過路口機率有改善
                        optimalSpeed = self.recommendSpeed
                        print("Plan B: OBU ID = %s +++++++++ Optimal speed = %d m/s ++++++++" % (self.OBU_ID, optimalSpeed))
                        traci.vehicle.setSpeed(self.OBU_ID, optimalSpeed)
                        self.OBU_RECOMMENDED_SPEED_INDICATOR = 0 # 已經計算過建議速度，將功能關閉
                    else: # if self.recommendSpeed == 0

                        # 相較於原始速度之通過機率，窮舉後所有速度之通過機率皆沒有改善
                        print("Plan C: 所有建議速度均沒有比原速好，採用緩慢減速機制")\

                        busCurTime = (traci.simulation.getTime() - RSUs['I1'].CycleAccumulated)
                        targetPhaseStartTime = RSUs['I1'].plan[0].phases[self.targetPhase].startTime

                        if (targetPhaseStartTime > busCurTime): #時相尚未開始
                            # 時間差t = 目標時相起始時間 - (當下模擬絕對時間 - 週期累計時間)
                            t = targetPhaseStartTime - busCurTime
                            print("targetPhaseStartTime > busCurTime / t = ", t)
                        else: # targetPhaseStartTime <= busCurTime
                            targetPhaseStartTime = RSUs['I1'].plan[1].phases[self.targetPhase].startTime
                            t = targetPhaseStartTime - busCurTime
                            print("targetPhaseStartTime <= busCurTime / t = ", t)

                        if self.direction in ['East', 'West']:  # 東西向
                            dist = round(abs(RSUs['I1'].location[0] - self.position[0]))  # 計算到路口的距離
                        elif self.direction in ['Nort', 'Sout']:  # 南北向
                            dist = round(abs(self.position[0]))  # 計算到路口的距離

                        self.acceleration = (dist - (self.currentSpeed * t * 2)) / t**2
                        print("dist = %d /  t = %d  / currentSpeed = %d / acceleration = %f" % (dist, t, self.currentSpeed , self.acceleration))
                        self.PLAN_C_INDICATOR = True  #開啟planC indicator
                        self.OBU_RECOMMENDED_SPEED_INDICATOR = 0 # 已經計算過建議速度，將功能關閉

                else:
                    print("OBU_RECOMMENDED_SPEED_INDICATOR = %d / self.currentSpeed = %d" % (self.OBU_RECOMMENDED_SPEED_INDICATOR, self.currentSpeed))
                    print("速度建議功能已被關閉")
            else: # if (result == False)
                # print("self.findTargetIntersections() return %s" % result)
                # print("OBU: %s 公車即將離開路網，重新開啟速度建議功能，將速度控制權還給SUMO" % self.OBU_ID)
                # # 因不確定是否車輛還有受速度控制，統一下指令將控制權還給SUMO
                # traci.vehicle.setSpeed(self.OBU_ID, -1)  # 引數-1 表示將控制權還給SUMO
                # self.OBU_RECOMMENDED_SPEED_INDICATOR = 1 # 重新開啟速度建議功能
                # self.PLAN_C_INDICATOR = False #將plan C indicator 關閉
                pass
        else:
            print("OBU_START_INDICATOR != 1  沒有開啟OBU功能")

        # 逐秒執行 plan C
        if (self.PLAN_C_INDICATOR == True):
            self.currentSpeed = self.currentSpeed + self.acceleration #Expected 減速度 = negative value
            print("Plan C: self.acceleration = %d / self.currentSpeed = %d" % (self.acceleration, self.currentSpeed))
            if (self.currentSpeed < 6): #不能讓車輛在路中停止，需要有個最小速度維持
                traci.vehicle.setSpeed(self.OBU_ID, 6)
            else:
                traci.vehicle.setSpeed(self.OBU_ID, self.currentSpeed)
        else:
            # print("no plan C executing")
            pass

    # 計算駕駛建議速度
    def calOptimalSpeed(self, RSUs): #輸入路口RSU物件
        # RSUs = {'I1':I1(RSU物件), 'I2':I2(RSU物件), ... }
        # 最大通過機率預設為 = 通過機率限制
        maxPassProb = self.passProbThreshold
        print("self.needOptIntersectionList = ", self.needOptIntersectionList)
        # for i in self.needOptIntersectionList: # 累計各路口通過機率
        #     maxPassProb = maxPassProb + self.intersectionPassProb[i]

        # 計算各速度下的通過機率
        maxSpeed = round((1 + self.MaxSpeedFactor) * self.maxSpeedLimit)  # 設定建議速度上限
        minSpeed = round((1 - self.MinSpeedFactor) * self.maxSpeedLimit)  # 設定建議速度下限
        originalSpeed = self.currentSpeed
        for v in range(minSpeed, maxSpeed):  # 從 minSpeed 到 maxSpeed 窮舉
            self.currentSpeed = v  # 將目前速度設為v

            for i in self.needOptIntersectionList:
                newPassProb = self.calPassProb(RSUs[i])  # 以此速度計算路口通過機率
                self.intersectionPassProb.update({i: newPassProb})  # 更新路口i的通過機率 intersectionPassProb list

             # 加總各路口通過機率成為totalPassProb
            totalPassProb = 0
            for i in self.needOptIntersectionList:
                totalPassProb = totalPassProb + self.intersectionPassProb[i]

            if (totalPassProb > maxPassProb):  # 若新計算結果大於舊的，則取代之
                print("速度 %d 之 路口通過總機率為 %f 比原本 %f 好" % (v, totalPassProb, maxPassProb))
                maxPassProb = totalPassProb
                self.recommendSpeed = v  # 新速度v作為建議速度
                print("OBU: %s 建議速度 = %d" % (self.OBU_ID, self.recommendSpeed))
            else:
                print("速度 %d 之 路口通過機率為 %f 沒有比原本 %f 好" % (v, totalPassProb, maxPassProb))
                self.currentSpeed = originalSpeed #將速度改回原始速度

    # 取得OBU目前資訊
    def getCurrentState(self):
        return self.OBU_ID, self.vehType, self.position, self.currentSpeed, self.direction, self.hostRSU, self.targetPhase, self.occupancy, self.duty, self.recommendSpeed, self.targetIntersections, self.targetIntersections_expectedArrivalTime, self.targetIntersections_redTimeDelay


    def __str__(self):
        return 'OBU(OBU_ID = {0}, vehType = {1}, position  = {2}, currentSpeed = {3}, direction = {4}, hostRSU = {5}, targetPhase = {6}, recommendSpeed = {7})'\
            .format(self.OBU_ID, self.vehType, self.position , self.currentSpeed, self.direction, self.hostRSU, self.targetPhase, self.recommendSpeed)



