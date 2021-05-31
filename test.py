
# a simple file writer object

# class MessageWriter(object):
#     def __init__(self, file_name):
#         self.file_name = file_name
#
#     def __enter__(self):
#         self.file = open(self.file_name, 'w')
#         return self.file
#
#     def __exit__(self):
#         self.file.close()
#
# # using with statement with MessageWriter
#
# with MessageWriter('my_file.txt') as xfile:
#     xfile.write('hello world')


import sys, os

# Disable
def blockPrint():
    sys.stdout = open(os.devnull, 'w')

# Restore
def enablePrint():
    sys.stdout = sys.__stdout__


print('This will print')

blockPrint()
print("This won't")

enablePrint()
print("This will too")