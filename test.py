import itertools
import configparser

# phasePool = itertools.cycle(['A', 'B', 'C', 'D'])
# cp = 1
# revisedPhasePool = itertools.islice(phasePool, cp, None)
# for item in revisedPhasePool:
#     print(item)
#     break
#
# print(1/0)
# config = configparser.ConfigParser()
# config.read('Config.ini')
# print(config['DEFAULT']['SPEED'])


sp = []
sp.append(dict({'rsu1': 123, 'rrr': 222}))
sp.append(dict({'rsu1': 155, 'rrr': 555}))
print(sp)

CURRENT_PHASE = range(1, 9, 1)
for i in CURRENT_PHASE:
    print(i)
