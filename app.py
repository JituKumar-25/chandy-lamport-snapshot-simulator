import os

from flask import Flask, render_template

from config import Config, BASE_DIR
from models import db
from routes import api, init_sim


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    os.makedirs(os.path.join(BASE_DIR, "database"), exist_ok=True)
    db.init_app(app)
    app.register_blueprint(api)

    @app.route("/")
    def dashboard():
        return render_template("dashboard.html")

    @app.route("/history")
    def history():
        return render_template("history.html")

    with app.app_context():
        db.create_all()          # database and tables are created automatically
        init_sim()               # loads the demo simulation
    return app


app = create_app()

if __name__ == "__main__":
    app.run(host=os.environ.get("HOST", "127.0.0.1"), port=5000, debug=False)
