path = r'src\nuevamente\storage\oci_client.py'
with open(path,'rb') as f:
    b = f.read()
new_b = bytearray()
i = 0
n = len(b)
while i < n:
    if b[i] == 92:
        if i+3 < n and b[i+1]==34 and b[i+2]==34 and b[i+3]==34:
            new_b.append(34); new_b.append(34); new_b.append(34)
            i += 4
            continue
    new_b.append(b[i])
    i += 1
with open(path,'wb') as f:
    f.write(bytes(new_b))
print('done')
