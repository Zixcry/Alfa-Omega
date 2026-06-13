from app import app, db, Usuario
with app.app_context():
    # Insertar un Superadmin para autorizar registros
    
    db.session.query(Usuario).filter(Usuario.rol == "Superadmin").delete()
    admin = Usuario(cedula="11223344", nombre="Supervisor General", departamento="Seguridad", rol="Superadmin", estado="Activo")
    # Insertar un Usuario normal
    
    db.session.query(Usuario).filter(Usuario.rol == "User").delete()
    user = Usuario(cedula="25667889", nombre="Diana Alvarez", departamento="Apto 5A", rol="User", estado="Activo")
    db.session.add_all([admin, user])
    db.session.commit()
print("¡Usuarios cargados con éxito!")