

class SignalPlan:

    def setAllParameters(self,planID,phaseOrder,cycle,offset,phases=[]):

        self.planID = planID
        self.phaseOrder = phaseOrder # ex. B0 00 01...
        self.cycle = cycle
        self.offset = offset
        self.phases = phases
        self.phaseNumber = len(phases)

    def __str__(self):
        return 'SignalPlan(planID = {0}, phaseOrder = {1}, cycle = {2}, offset = {3}, phases = {4})'\
            .format(self.planID, self.phaseOrder, self.cycle, self.offset, self.phases)


class Phase(SignalPlan):

    def __init__(self, phaseID, startTime, greenSplit, green, Gmin, Gmax, yellow, allRed, pedFlash, pedRed, IsAdjustable, MAX_ADJUST_RATIO):

        self.phaseID = phaseID
        #self.phaseOrder = phaseOrder
        self.name = 0
        self.startTime = startTime
        self.greenSplit = greenSplit
        self.green = green
        self.Gmin = Gmin
        self.Gmax = Gmax
        self.yellow = yellow
        self.allRed = allRed
        self.pedFlash = pedFlash
        self.pedRed = pedRed

        self.IsAdjustable = IsAdjustable
        self.IsInUncontrollableStep = False  # 是否已經在無法控制的步階
        self.EXTENT_LIMIT = round(green * MAX_ADJUST_RATIO)  # 允許延長最大秒數
        self.TRUNCATION_LIMIT = round(-(green * MAX_ADJUST_RATIO))  # 允許縮短最大秒數
        self.totalAdjustableAmount = self.EXTENT_LIMIT + self.TRUNCATION_LIMIT  # 最大允許調整秒數

    def setParameters(self, phaseID, name, startTime, green, Gmax, Gmin, yellow, allRed,
                      EXTENT_LIMIT, TRUNCATION_LIMIT):
        self.planID = phaseID
        #self.phaseOrder = phaseOrder
        self.name = name
        self.startTime = startTime
        self.green = green
        self.Gmax = Gmax
        self.Gmin = Gmin
        self.yellow = yellow
        self.allRed = allRed
        self.TRUNCATION_LIMIT = TRUNCATION_LIMIT
        self.EXTENT_LIMIT = EXTENT_LIMIT

    def setIsInUncontrollableStep(self, IsInUncontrollableStep):
        self.IsInUncontrollableStep = IsInUncontrollableStep

    def setAdjustable(self, IsAdjustable):
        self.IsAdjustable = IsAdjustable

    def __str__(self):
        return 'Phase(phaseID = {0}, phaseName = {1}, startTime = {2}, green = {3}, yellow = {4}, allRed = {5})' \
            .format(self.phseID, self.name, self.startTime, self.green, self.yellow, self.allRed)

