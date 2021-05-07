import traci

class TriggerPoint():

    def __init__(self, ID, location, type, direction, RSU, groupID):

        self.ID = ID
        self.location = location
        self.type = type
        self.direction = direction
        self.serviceRSU = RSU
        self.setviceIntersectionGroup = groupID

    def setParameters(self, ID, location, type, direction, RSU, groupID):
        return 0

    # 觸發點偵測結果
    def detectResult(self):
        return 0

    def __str__(self):
        return 'Phase(phaseOrder = {0}, phaseName = {1}, startTime = {2}, green = {3}, yellow = {4}, allRed = {5})' \
            .format(self.phaseOrder, self.name, self.startTime, self.green, self.yellow, self.allRed)

