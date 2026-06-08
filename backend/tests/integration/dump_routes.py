from main import app

for route in app.routes:
    print(getattr(route, "path", None), getattr(route, "name", None), getattr(route, "methods", None))
