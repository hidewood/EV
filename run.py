"""启动入口。"""
from backend.app import create_app, init_db

app = create_app()

with app.app_context():
    init_db()

if __name__ == "__main__":
    print("Server running at http://localhost:8080")
    print("User client:  http://localhost:8080/user-client/index.html")
    print("Admin client: http://localhost:8080/admin-client/index.html")
    app.run(debug=False, host="0.0.0.0", port=8080)
