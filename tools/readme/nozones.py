import sys, pcbnew
src, dst = sys.argv[1], sys.argv[2]
b = pcbnew.LoadBoard(src)
for z in list(b.Zones()):
    b.Remove(z)
pcbnew.SaveBoard(dst, b)
print("nozones", dst)
