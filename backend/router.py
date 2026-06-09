def register_routes(app):
    from .controllers.auth_controller import bp as auth_bp
    from .controllers.request_controller import bp as charging_bp
    from .controllers.bill_controller import bp as bill_bp
    from .controllers.pile_controller import bp as pile_bp
    from .controllers.queue_controller import bp as queue_bp
    from .controllers.admin_controller import bp as admin_bp
    from .controllers.external_controller import bp as external_bp

    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(charging_bp, url_prefix="/api/charging")
    app.register_blueprint(bill_bp, url_prefix="/api/bill")
    app.register_blueprint(pile_bp, url_prefix="/api/pile")
    app.register_blueprint(queue_bp, url_prefix="/api/queue")
    app.register_blueprint(admin_bp, url_prefix="/api/admin")
    app.register_blueprint(external_bp)
