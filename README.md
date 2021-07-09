# tainanBusTSP SuperMatrix

台南整合型公車優先通行 超級矩陣主程式

## How to use it?
- Step 1 Prepare two files:  (1) SignalTiming.csv (2) Config.ini 
- Step 2 Run python file: GenerateSuperMatrix.py
- Step 3 Wait for executing (Worst case: 30min, Average case: 10min)
- Step 4 The super matrix file are located in the folder designated in Config.ini.



## Changes Log

**20210602**
- SPEED parameter is now moved to "_ _init_ _" as a argument (in CloudControl) and no longer avilable in Config.ini
  - To initialize CloudControl Object, you now need to specify argument "speed".  
  - For SuperMatrixGenerate.py, the default value of argument "speed" is 10 (m/s). 


**20210531**
- Add a function: control enable or diable PYTHON STANDARD PRINT():

  ***How to use: In config.ini there is a variable named "STD_PRINT", default value is 0.***

  * STD_PRINT = 0 -> Disable PYTHON PRINT()
  * STD_PRINT = 1 -> Enable PYTHON PRINT()

