
import math
import TainanTSP_Class
import time
from distutils.util import strtobool
import configparser
# 先將column寫入csv檔
import csv
import os.path
from datetime import date
import argparse


start_time = time.time()


def makeOutputFile(OUTPUT_FILE_PATH, OUTPUT_WITH_INPUT_COLUMN, resultList, sp, RSU_ID):

    today = date.today()
    todayDate = today.strftime("%Y%m%d")

    filePath = OUTPUT_FILE_PATH + '/' + RSU_ID + '   _' + str(sp) + '_' + todayDate + '.csv'

    if os.path.isfile(filePath):
        print("File exist")
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


    with open(filePath, 'a', newline='\n') as csvfile:
        writer = csv.writer(csvfile)
        # for row in resultList:
        #     writer.writerow(row)
        writer.writerows(resultList)

    csvfile.close()

    return 0

def readSignalCSV(SIGNAL_PLAN_FILE_NAME, assignedPlanID):
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
            planID = int(row['PlanID'])
            if planID == assignedPlanID:

                phaseOrder = row['PhaseOrder']
                offset = row['Offset']
                RSU_ID = row['RSU_ID']

                Phase = {'PhaseID': int(row['PhaseID'])-1, 'Green': int(row['Green']), 'PedGreenFlash': int(row['PedFlash']), 'Yellow': int(row['Yellow']),
                         'AllRed': int(row['AllRed']), 'PedRed': int(row['PedRed']), 'Gmin': int(row['MinGreen']),
                         'Gmax': int(row['MaxGreen']), 'IsAdjustable': 1}

                Plan.append(Phase)

    return Plan, phaseOrder, offset, RSU_ID


if __name__ == '__main__':
    # Config File Parser
    config = configparser.ConfigParser()
    config.read('Config.ini')
    #assignedPlanID = int(config['OPTIONS']['ASSIGENED_PLAN_NUM'])
    SIGNAL_PLAN_FILE_NAME = config['DEFAULT']['SIGNAL_PLAN_FILE_NAME']
    OUTPUT_WITH_INPUT_COLUMN = False
    OUTPUT_FILE_PATH = config['DEFAULT']['OUTPUT_FILE_PATH']

    parser = argparse.ArgumentParser(description="SuperMaxtrix Generation")

    parser.add_argument("-maxEXT", help="Signal adjust upper bound percentage (Unit: Integer)", type=int)
    parser.add_argument("-maxTRU", help="Signal adjust lower bound percentage (Unit: Integer)", type=int)
    parser.add_argument("-speed", help="Speed (Unit: m/s)", type=int)
    parser.add_argument("-noAdjustGreenLength", help="if the green length of a phase is less than this value, the phase will not be controlled. (Unit: Integer)", type=int)
    parser.add_argument("-assignedPlanNumber", help="the plan number that you hope SUPERMATRIX generate for (Unit: Integer)", type=int)
    parser.print_help()
    args = parser.parse_args()
    assignedPlanNumber = args.assignedPlanNumber
    SP = readSignalCSV(SIGNAL_PLAN_FILE_NAME, assignedPlanNumber)

    Plan = SP[0]
    planParameters = {'phaseOrder': SP[1], 'offset': SP[2]}

    CL = TainanTSP_Class.CloudControl(SP=Plan, planParameters=planParameters, speed=args.speed,
                                      MAX_EXTENT_ADJ_RATIO=args.maxEXT, MAX_TRUNCATION_ADJ_RATIO=args.maxTRU,
                                      PASS_PROBABILITY_Threshold=80, NoAdjustGreenLength=args.noAdjustGreenLength)

    DIST = range(10, 510, 10)
    # CURRENT_PHASE = range(0, len(RSUs['rsu1'].plan[sp].phases), 1)  # len(RSUs['rsu1'].plan[sp].phases)
    CURRENT_PHASE = range(1, 9, 1)
    # PRIORITIZED_PHASE = range(0, len(RSUs['rsu1'].plan[sp].phases), 1)
    PRIORITIZED_PHASE = range(1, 9, 1)

    resultList = []
    for dist in DIST:
        for speed in [CL.SPEED]:
            arrivalTime = int(dist / speed)
            shiftAdjAmount = [0, 0, 0, 0, 0, 0, 0, 0]
            for cp in CURRENT_PHASE:
                REMAINING_TIME = range(1, 200, 2)
                for rt in REMAINING_TIME:
                    # 時相剩於秒數(rt)
                    # 說明：(1) 控制器的rt指 剩餘綠燈 + 行閃 + 行紅 + 黃燈 + 全紅
                    #           (2) 本程式rt指 剩餘綠燈秒數
                    # 綜合以上兩者需進行判斷轉換
                    # rt_for_passProb = 用於計算通過機率的rt
                    # rt_for_calStrategy = 用於計算優先策略的rt

                    rt_for_resume = rt  # 備份rt
                    for pp in PRIORITIZED_PHASE:

                        if ((cp not in range(1, len(Plan)+1, 1)) or (pp not in range(1, len(Plan)+1, 1)) or (dist >= 200)):
                            result = [dist, cp, rt, pp, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]

                            # makeOutputFile(OUTPUT_FILE_PATH=OUTPUT_FILE_PATH, OUTPUT_WITH_INPUT_COLUMN=OUTPUT_WITH_INPUT_COLUMN,
                            #                result=result, sp=assignedPlanID)

                        else:

                            if (arrivalTime == 1 and cp==1 and pp==3 and rt == 1):
                                print("xxxx")

                            result = CL.run(arrivalTime=arrivalTime, cp=cp, pp=pp, rt=rt)
                            result[0] = dist

                            times_after_step2 = Plan[cp-1]['PedGreenFlash'] + Plan[cp-1]['Yellow'] + Plan[cp-1]['AllRed'] + Plan[cp-1]['PedRed']
                            times_at_step1 = rt - times_after_step2

                            if (cp == pp and times_at_step1 > 0 and times_at_step1 < 5):
                                shiftAdjAmount[cp-1] = shiftAdjAmount[cp-1] + result[cp+3]
                                result[cp+3] = 0

                            if (cp == pp and times_at_step1 > 0 and times_at_step1 == 5):
                                result[cp+3] = result[cp+3] + shiftAdjAmount[cp-1]
                                shiftAdjAmount[cp-1] = 0

                        if OUTPUT_WITH_INPUT_COLUMN:
                            input = result
                        else:
                            input = result[4:]  # 前面0~3為dist, cp, pp, rt截掉

                        resultList.append(input)

                            # makeOutputFile(OUTPUT_FILE_PATH=OUTPUT_FILE_PATH, OUTPUT_WITH_INPUT_COLUMN=OUTPUT_WITH_INPUT_COLUMN,
                            #                result=result, sp=assignedPlanID)

    makeOutputFile(OUTPUT_FILE_PATH=OUTPUT_FILE_PATH, OUTPUT_WITH_INPUT_COLUMN=OUTPUT_WITH_INPUT_COLUMN,
                   resultList=resultList, sp=assignedPlanNumber, RSU_ID=SP[3])

    print("--- 執行共花了 %s seconds ---" % (time.time() - start_time))


