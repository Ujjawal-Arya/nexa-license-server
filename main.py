from fastapi import FastAPI, HTTPException, Header
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from pymongo import MongoClient
import os
from dotenv import load_dotenv

# 1. Load variables from .env file
load_dotenv()

app = FastAPI(title="NEXA License Server (MongoDB)")

# 2. Get configurations from .env
MONGO_URI = os.getenv("MONGO_URI")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "ujjawal_admin_123")

# 3. Connect to MongoDB Atlas
try:
    if not MONGO_URI:
        print("⚠️ Warning: MONGO_URI is missing in .env file!")
        
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    db = client["nexa_database"]
    collection = db["licenses"]
    
    # Test connection
    client.admin.command('ping')
    print("SUCCESS: Connected to MongoDB Atlas!")
except Exception as e:
    print(f"ERROR: MongoDB Connection Error: {e}")

# 4. Request Models
class VerifyRequest(BaseModel):
    key: str
    hwid: str

class ManageKeyRequest(BaseModel):
    admin_password: str
    key: str

# 5. Core Endpoints
@app.post("/verify")
def verify_license(req: VerifyRequest):
    key = req.key.strip()
    
    # MongoDB me key search karein
    doc = collection.find_one({"key": key})
    
    if not doc:
        return {"status": "invalid", "message": "Invalid License Key"}
        
    bound_hwid = doc.get("hwid", "")
    
    if bound_hwid == "":
        # Key unused hai, naye device ke hwid se bind kar do
        collection.update_one({"key": key}, {"$set": {"hwid": req.hwid}})
        return {"status": "valid", "message": "License Activated and Bound to Device!"}
        
    elif bound_hwid == req.hwid:
        # Same device se request aayi hai
        return {"status": "valid", "message": "License Verified!"}
        
    else:
        # Dusre device se request aayi hai
        return {"status": "blocked", "message": "Access Denied: Key already used on another device!"}

@app.post("/add_key")
def add_new_key(req: ManageKeyRequest):
    if req.admin_password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")
        
    # Check karein agar key pehle se exist karti hai
    if collection.find_one({"key": req.key}):
        return {"message": "Key already exists!"}
        
    # Nayi key insert karein, default hwid empty rakhein
    collection.insert_one({"key": req.key, "hwid": ""})
    return {"message": f"Successfully added new key: {req.key}"}

@app.post("/reset_key")
def reset_key(req: ManageKeyRequest):
    if req.admin_password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")
        
    # Device ka hwid hata dein
    result = collection.update_one({"key": req.key}, {"$set": {"hwid": ""}})
    
    if result.matched_count == 0:
        return {"message": "Key not found!"}
        
    return {"message": f"Successfully reset key: {req.key} (Unbound from HWID)"}

@app.post("/delete_key")
def delete_key(req: ManageKeyRequest):
    if req.admin_password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")
        
    # Database se key delete karein
    result = collection.delete_one({"key": req.key})
    
    if result.deleted_count == 0:
        return {"message": "Key not found!"}
        
    return {"message": f"Successfully deleted key: {req.key}"}

@app.post("/list_keys")
def list_keys(req: ManageKeyRequest):
    if req.admin_password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Unauthorized")
        
    # MongoDB se saari keys fetch karein
    keys = {}
    for doc in collection.find():
        keys[doc["key"]] = doc.get("hwid", "")
        
    return {"keys": keys}

@app.get("/")
def home():
    return {"message": "NEXA License Server (MongoDB) is Running. Go to /admin for the Control Panel."}

# HTML Admin Panel
@app.get("/admin", response_class=HTMLResponse)
def admin_page():
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>NEXA Admin Panel</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; background: #121212; color: white; }
            input, button { padding: 10px; margin: 5px 0; width: 100%; box-sizing: border-box; }
            button { background: #4CAF50; color: white; border: none; cursor: pointer; font-weight: bold; }
            button.danger { background: #f44336; }
            button.warn { background: #ff9800; }
            .card { background: #1e1e1e; padding: 20px; border-radius: 8px; margin-bottom: 20px; }
            pre { background: #000; padding: 10px; border-radius: 5px; overflow-x: auto; }
        </style>
    </head>
    <body>
        <h2>NEXA Admin Panel 🛡️</h2>
        
        <div class="card">
            <label>Admin Password:</label>
            <input type="password" id="admin_pass" placeholder="Enter Admin Password">
        </div>

        <div class="card">
            <h3>Add New Key</h3>
            <input type="text" id="new_key" placeholder="Enter New Key (e.g. RAHUL-123)">
            <button onclick="manageKey('add_key', 'new_key')">➕ Create Key</button>
        </div>

        <div class="card">
            <h3>Manage Existing Keys</h3>
            <input type="text" id="manage_key" placeholder="Enter Existing Key">
            <button class="warn" onclick="manageKey('reset_key', 'manage_key')">🔄 Reset Key (Unbind HWID)</button>
            <button class="danger" onclick="manageKey('delete_key', 'manage_key')">🗑️ Delete Key</button>
        </div>

        <div class="card">
            <h3>View All Licenses</h3>
            <button onclick="listKeys()">📜 Load Database</button>
            <pre id="output">Results will appear here...</pre>
        </div>

        <script>
            async function manageKey(endpoint, inputId) {
                const password = document.getElementById("admin_pass").value;
                const key = document.getElementById(inputId).value;
                if (!password || !key) return alert("Please enter both password and key!");

                const res = await fetch("/" + endpoint, {
                    method: "POST",
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify({admin_password: password, key: key})
                });
                const data = await res.json();
                document.getElementById("output").innerText = JSON.stringify(data, null, 2);
            }

            async function listKeys() {
                const password = document.getElementById("admin_pass").value;
                if (!password) return alert("Please enter Admin Password!");

                const res = await fetch("/list_keys", {
                    method: "POST",
                    headers: {"Content-Type": "application/json"},
                    body: JSON.stringify({admin_password: password, key: ""})
                });
                const data = await res.json();
                document.getElementById("output").innerText = JSON.stringify(data.keys || data, null, 2);
            }
        </script>
    </body>
    </html>
    """
    return html_content
