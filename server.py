from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
import json, os, sqlite3, urllib.request, urllib.parse, math, random, string
try:
    import psycopg
except ImportError:
    psycopg = None

ROOT=os.path.dirname(os.path.abspath(__file__))
PUBLIC=os.path.join(ROOT,"public")
DB=os.path.join(ROOT,"where_should_we_eat.db")
PORT=int(os.environ.get("PORT","8000"))
HOST=os.environ.get("HOST","0.0.0.0")

def db():
    url=os.environ.get("DATABASE_URL","").strip()
    if url and psycopg:
        return PGConn(url)
    con=sqlite3.connect(DB, timeout=10)
    con.row_factory=sqlite3.Row
    return con

class PGConn:
    def __init__(self,url):
        self.con=psycopg.connect(url, autocommit=True)
    def execute(self,sql,args=()):
        # Translate the small SQL dialect used by this app.
        sql=sql.replace("?", "%s")
        sql=sql.replace("INTEGER PRIMARY KEY AUTOINCREMENT","BIGSERIAL PRIMARY KEY")
        sql=sql.replace("CURRENT_TIMESTAMP","CURRENT_TIMESTAMP")
        sql=sql.replace("ON CONFLICT(code,member,restaurant_id) DO UPDATE SET value=excluded.value",
                        "ON CONFLICT(code,member,restaurant_id) DO UPDATE SET value=EXCLUDED.value")
        cur=self.con.cursor()
        cur.execute(sql,args)
        if cur.description:
            cols=[d.name for d in cur.description]
            return [dict(zip(cols,row)) for row in cur.fetchall()]
        return []
    def executescript(self,sql):
        for stmt in sql.split(";"):
            if stmt.strip(): self.execute(stmt)
    def commit(self): pass
    def close(self): self.con.close()

def init_db():
    con=db()
    con.executescript("""
    CREATE TABLE IF NOT EXISTS sessions(code TEXT PRIMARY KEY, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS members(id BIGSERIAL PRIMARY KEY, code TEXT, name TEXT, joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, UNIQUE(code,name));
    CREATE TABLE IF NOT EXISTS votes(id BIGSERIAL PRIMARY KEY, code TEXT, member TEXT, restaurant_id TEXT, value INTEGER, UNIQUE(code,member,restaurant_id));
    """)
    con.commit(); con.close()

def send(h,d,status=200):
    raw=json.dumps(d).encode()
    h.send_response(status)
    h.send_header("Content-Type","application/json; charset=utf-8")
    h.send_header("Content-Length",str(len(raw)))
    h.send_header("Cache-Control","no-store")
    h.end_headers()
    h.wfile.write(raw)

def newcode():
    return ''.join(random.choice(string.ascii_uppercase+string.digits) for _ in range(6))

def distance_km(a,b,c,d):
    R=6371; p=math.pi/180
    x=math.sin((c-a)*p/2)**2+math.cos(a*p)*math.cos(c*p)*math.sin((d-b)*p/2)**2
    return R*2*math.atan2(math.sqrt(x),math.sqrt(1-x))

def get_restaurants(lat,lon,radius):
    r=int(max(1,min(float(radius),20))*1000)
    q='[out:json][timeout:30];(nwr["amenity"="restaurant"](around:%s,%s,%s);nwr["amenity"="fast_food"](around:%s,%s,%s);nwr["amenity"="cafe"](around:%s,%s,%s););out center tags;' % (r,lat,lon,r,lat,lon,r,lat,lon)
    last=None
    for endpoint in ["https://overpass-api.de/api/interpreter","https://overpass.private.coffee/api/interpreter"]:
        try:
            req=urllib.request.Request(endpoint,data=urllib.parse.urlencode({"data":q}).encode(),headers={"User-Agent":"WhereShouldWeEat/3.0"})
            with urllib.request.urlopen(req,timeout=40) as z: data=json.loads(z.read().decode())
            out=[]; seen=set()
            for e in data.get("elements",[]):
                p=e.get("center",e); t=e.get("tags",{})
                name=t.get("name")
                if not name or "lat" not in p or "lon" not in p: continue
                key=(str(name).strip().lower(),round(float(p["lat"]),4),round(float(p["lon"]),4))
                if key in seen: continue
                seen.add(key)
                out.append({
                    "id":f'{e["type"]}-{e["id"]}',"name":name,"type":t.get("amenity","restaurant"),
                    "cuisine":t.get("cuisine","").replace("_"," "),"distance":round(distance_km(lat,lon,float(p["lat"]),float(p["lon"])),1),
                    "lat":float(p["lat"]),"lon":float(p["lon"]),
                    "address":" ".join(x for x in [t.get("addr:housenumber"),t.get("addr:street"),t.get("addr:city")] if x),
                    "opening":t.get("opening_hours",""),"phone":t.get("phone",""),"website":t.get("website","")
                })
            out.sort(key=lambda x:x["distance"])
            return out[:100]
        except Exception as e: last=e
    raise last or RuntimeError("Restaurant data unavailable")

class Handler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs):
        super().__init__(*args,directory=PUBLIC,**kwargs)

    def log_message(self,fmt,*args):
        pass

    def do_GET(self):
        u=urlparse(self.path)
        if u.path=="/api/health":
            send(self,{"ok":True,"version":"3.0"}); return
        if u.path=="/api/session":
            c=parse_qs(u.query).get("code",[""])[0].upper()
            con=db()
            exists=con.execute("SELECT 1 FROM sessions WHERE code=?",(c,)).fetchone()
            members=[r["name"] for r in con.execute("SELECT name FROM members WHERE code=? ORDER BY id",(c,))] if exists else []
            con.close(); send(self,{"ok":bool(exists),"members":members}); return
        super().do_GET()

    def do_POST(self):
        u=urlparse(self.path)
        try: body=json.loads(self.rfile.read(int(self.headers.get("Content-Length","0"))) or b"{}")
        except Exception: send(self,{"ok":False,"error":"Invalid request"},400); return

        if u.path=="/api/session/create":
            name=str(body.get("name","Host")).strip()[:40] or "Host"; c=newcode(); con=db()
            con.execute("INSERT INTO sessions(code) VALUES(?)",(c,))
            con.execute("INSERT INTO members(code,name) VALUES(?,?)",(c,name))
            con.commit(); con.close(); send(self,{"ok":True,"code":c,"name":name}); return

        if u.path=="/api/session/join":
            c=str(body.get("code","")).strip().upper(); name=str(body.get("name","Guest")).strip()[:40] or "Guest"; con=db()
            if not con.execute("SELECT 1 FROM sessions WHERE code=?",(c,)).fetchone():
                con.close(); send(self,{"ok":False,"error":"That group code does not exist."},404); return
            try: con.execute("INSERT INTO members(code,name) VALUES(?,?)",(c,name)); con.commit()
            except sqlite3.IntegrityError: pass
            ms=[r["name"] for r in con.execute("SELECT name FROM members WHERE code=? ORDER BY id",(c,))]
            con.close(); send(self,{"ok":True,"code":c,"name":name,"members":ms}); return

        if u.path=="/api/members":
            c=str(body.get("code","")).upper(); con=db()
            ms=[r["name"] for r in con.execute("SELECT name FROM members WHERE code=? ORDER BY id",(c,))]
            con.close(); send(self,{"ok":True,"members":ms}); return

        if u.path=="/api/restaurants":
            try:
                rs=get_restaurants(float(body["lat"]),float(body["lon"]),float(body.get("radius",5)))
                send(self,{"ok":True,"restaurants":rs})
            except Exception: send(self,{"ok":False,"error":"The free restaurant service is busy. Try again in a moment."},502)
            return

        if u.path=="/api/vote":
            c=str(body.get("code","")).upper(); m=str(body.get("member","")).strip()[:40]; rid=str(body.get("restaurant_id","")); v=int(body.get("value",0))
            if v not in (-1,0,1): send(self,{"ok":False,"error":"Invalid vote"},400); return
            con=db()
            con.execute("""INSERT INTO votes(code,member,restaurant_id,value) VALUES(?,?,?,?)
                           ON CONFLICT(code,member,restaurant_id) DO UPDATE SET value=excluded.value""",(c,m,rid,v))
            con.commit(); con.close(); send(self,{"ok":True}); return

        if u.path=="/api/results":
            c=str(body.get("code","")).upper(); con=db()
            rows=con.execute("""SELECT restaurant_id,
                SUM(CASE WHEN value=1 THEN 1 ELSE 0 END) likes,
                SUM(CASE WHEN value=0 THEN 1 ELSE 0 END) maybes,
                SUM(CASE WHEN value=-1 THEN 1 ELSE 0 END) dislikes
                FROM votes WHERE code=? GROUP BY restaurant_id""",(c,)).fetchall()
            con.close(); send(self,{"ok":True,"results":[dict(r) for r in rows]}); return

        send(self,{"ok":False,"error":"Unknown endpoint"},404)

init_db()
if __name__=="__main__":
    print("Where Should We Eat V3 running at http://localhost:%s" % PORT)
    print("Keep this window open.")
    ThreadingHTTPServer((HOST,PORT),Handler).serve_forever()
