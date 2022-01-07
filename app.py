from duzhibot.app import App, bp, main

__all__ = ["app"]

app = App(__name__, static_url_path="")
app.register_blueprint(bp)

if __name__ == "__main__":
    main(app)
