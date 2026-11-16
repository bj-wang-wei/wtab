import json
p = json.loads('[{"id":2},{"id":"3"}]')
print([type(x["id"]).__name__ for x in p])
print(2 in {e["id"] for e in p}, "| '2' in {str(e['id']) for e in p}")
