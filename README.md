# tainanBusTSP SuperMatrix

台南整合型公車優先通行 超級矩陣主程式

## How to use it?
- Step 1 Prepare two files:  (1) SignalTiming.csv (2) Config.ini 
- Step 2 Run python file: GenerateSuperMatrix.py
- Step 3 Wait for executing (Worst case: 30min, Average case: 10min)
- Step 4 The super matrix file are located in the folder designated in Config.ini.



## Changes Log

**20210709**
- Config.ini
  - some paras originally read in Config.ini are now changed to be read by argparse.
    - MAX_ADJUST_RATIO  / PASS_PROBABILITY_Threshold / ASSIGENED_PLAN_NUM
- GenerateSuperMatrix.py
  - Add corresponding parars for argparse.
- RSU.py
  - nullified a deprecated function: updateCycleAccumulated()
- TainanTSP_Class.py
  - Add several arguments into CloudControl constructor: MAX_EXTENT_ADJ_RATIO, MAX_TRUNCATION_ADJ_RATIO, PASS_PROBABILITY_Threshold, NoAdjustGreenLength
  - Add a compare statement on phaseAdjustable for NoAdjustGreenLength
  - Bug fix: Revise the statement on PhaseTruncation
    - ***BUG: In the past, the amount of non-prioritized phase truncation are calculated from currrent phase until prioritized phase (not included) with the function [currentPhase:prioritizedPhase]*** 
    - THIS GOES WRONG WHEN the order of prioritizedPhase is less than currentPhase. (Eg. [2:1] -> RESULT: DO NOTHING, Acutually I want to calculate from phase 2 to the end phase of current cycle.)

**20210602**
- SPEED parameter is now moved to "_ _init_ _" as a argument (in CloudControl) and no longer avilable in Config.ini
  - To initialize CloudControl Object, you now need to specify argument "speed".  
  - For SuperMatrixGenerate.py, the default value of argument "speed" is 10 (m/s). 


**20210531**
- Add a function: control enable or diable PYTHON STANDARD PRINT():

  ***How to use: In config.ini there is a variable named "STD_PRINT", default value is 0.***

  * STD_PRINT = 0 -> Disable PYTHON PRINT()
  * STD_PRINT = 1 -> Enable PYTHON PRINT()

