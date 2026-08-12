WHERE SHOULD WE EAT — V3.1 PUBLIC READY

LOCAL:
Double-click START_APP.bat and open http://localhost:8000

PUBLIC:
This version supports PostgreSQL through DATABASE_URL and binds to the hosting platform's port.
For Render:
1. Push this folder to GitHub.
2. Create a Render Web Service from the repo.
3. Build: pip install -r requirements.txt
4. Start: python server.py
5. Create a PostgreSQL database on Render and set DATABASE_URL to its Internal Database URL.
6. Deploy.

For a first public test, Render's free web service + PostgreSQL setup may be subject to current platform limits/availability. Check the current Render dashboard pricing before creating resources.

SECURITY NOTE:
This is a hobby/public prototype. Group codes are intentionally simple. Before a large public launch, add rate limiting, session authentication, input validation, CSRF protection, abuse controls, and a persistent production database plan.
