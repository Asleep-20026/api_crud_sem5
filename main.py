from fastapi import FastAPI, HTTPException, Depends, Query
from sqlalchemy import create_engine, Column, Integer, String, ForeignKey, DECIMAL
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from pydantic import BaseModel, Field
from typing import List, Optional
from sqlalchemy import func  # Añade esta importación al inicio del archivo
from sqlalchemy import text 

import urllib.parse

# Configuración de la conexión a Azure SQL Database
server = "server-android.database.windows.net"
database = "db_android"
username = "sqlserver"
password = "@sql123456"  # Contraseña incluida

# Codificar la contraseña para URL
encoded_password = urllib.parse.quote_plus(password)

# URL de conexión para SQLAlchemy con formato específico para Azure SQL
connection_string = f"mssql+pyodbc://{username}:{encoded_password}@{server}/{database}?driver=ODBC+Driver+18+for+SQL+Server"

# Opciones de conexión adicionales para Azure SQL
connection_args = {
    "Encrypt": "yes",
    "TrustServerCertificate": "no",
    "Connection Timeout": "30"
}

# Crear URL completa
params = "&".join([f"{key}={value}" for key, value in connection_args.items()])
DB_URL = f"{connection_string}&{params}"

# Crear motor con opciones de conexión
engine = create_engine(DB_URL, echo=True)  # echo=True para ver las consultas SQL generadas
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Definir el modelo de la base de datos
Base = declarative_base()

class Categoria(Base):
    __tablename__ = "categoria"
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    nombre = Column(String(50), nullable=False)

class Producto(Base):
    __tablename__ = "producto"
    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(50), nullable=False)
    categoria_id = Column(Integer, ForeignKey("categoria.id"), nullable=False)
    precio = Column(DECIMAL(20,2), nullable=False)
    stock = Column(Integer, nullable=False)
    url = Column(String(200), nullable=False)

# Modelos Pydantic para validación de datos
class CategoriaBase(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=50)

class CategoriaCreate(CategoriaBase):
    pass

class CategoriaResponse(CategoriaBase):
    id: int
    
    class Config:
        orm_mode = True

class ProductoBase(BaseModel):
    nombre: str = Field(..., min_length=1, max_length=50)
    categoria_id: int
    precio: float = Field(..., gt=0)
    stock: int = Field(..., ge=0)
    url: str = Field(..., min_length=1, max_length=200)

class ProductoCreate(ProductoBase):
    pass

class ProductoResponse(ProductoBase):
    id: int
    
    class Config:
        orm_mode = True

# Instancia de FastAPI
app = FastAPI(title="API de Tienda", description="API para gestionar categorías y productos")

# Verificar conexión a la base de datos
def test_db_connection():
    try:
        with engine.connect() as conn:
            return True
    except Exception as e:
        print(f"Error de conexión: {e}")
        return False

# Dependencia para obtener la sesión de la base de datos
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# Ruta para verificar la conexión
@app.get("/test-connection")
def test_connection():
    if test_db_connection():
        return {"status": "Conexión exitosa a la base de datos"}
    else:
        raise HTTPException(status_code=500, detail="No se pudo conectar a la base de datos")

@app.post("/categorias/", response_model=CategoriaResponse)
def crear_categoria(categoria: CategoriaCreate, db: Session = Depends(get_db)):
    try:
        # Usar text() para ejecutar consulta SQL
        result = db.execute(text("SELECT MAX(id) FROM categoria")).scalar()
        nuevo_id = 1 if result is None else result + 1
        
        nueva_categoria = Categoria(id=nuevo_id, nombre=categoria.nombre)
        db.add(nueva_categoria)
        db.commit()
        db.refresh(nueva_categoria)
        return nueva_categoria
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al crear categoría: {str(e)}")

@app.get("/categorias/", response_model=List[CategoriaResponse])
def listar_categorias(db: Session = Depends(get_db)):
    try:
        return db.query(Categoria).all()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al listar categorías: {str(e)}")

@app.get("/categorias/{categoria_id}", response_model=CategoriaResponse)
def obtener_categoria(categoria_id: int, db: Session = Depends(get_db)):
    try:
        categoria = db.query(Categoria).filter(Categoria.id == categoria_id).first()
        if not categoria:
            raise HTTPException(status_code=404, detail="Categoría no encontrada")
        return categoria
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener categoría: {str(e)}")

@app.put("/categorias/{categoria_id}", response_model=CategoriaResponse)
def actualizar_categoria(categoria_id: int, categoria: CategoriaCreate, db: Session = Depends(get_db)):
    try:
        db_categoria = db.query(Categoria).filter(Categoria.id == categoria_id).first()
        if not db_categoria:
            raise HTTPException(status_code=404, detail="Categoría no encontrada")
        
        db_categoria.nombre = categoria.nombre
        db.commit()
        db.refresh(db_categoria)
        return db_categoria
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al actualizar categoría: {str(e)}")

@app.delete("/categorias/{categoria_id}")
def eliminar_categoria(categoria_id: int, db: Session = Depends(get_db)):
    try:
        categoria = db.query(Categoria).filter(Categoria.id == categoria_id).first()
        if not categoria:
            raise HTTPException(status_code=404, detail="Categoría no encontrada")
        
        # Verificar si hay productos asociados
        productos = db.query(Producto).filter(Producto.categoria_id == categoria_id).first()
        if productos:
            raise HTTPException(status_code=400, detail="No se puede eliminar la categoría porque tiene productos asociados")
        
        db.delete(categoria)
        db.commit()
        return {"mensaje": "Categoría eliminada correctamente"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al eliminar categoría: {str(e)}")

# 📌 CRUD para Producto
@app.post("/productos/", response_model=ProductoResponse)
def crear_producto(producto: ProductoCreate, db: Session = Depends(get_db)):
    try:
        # Verificar si existe la categoría
        categoria = db.query(Categoria).filter(Categoria.id == producto.categoria_id).first()
        if not categoria:
            raise HTTPException(status_code=404, detail="La categoría especificada no existe")
        
        nuevo_producto = Producto(
            nombre=producto.nombre,
            categoria_id=producto.categoria_id,
            precio=producto.precio,
            stock=producto.stock,
            url=producto.url
        )
        
        db.add(nuevo_producto)
        db.commit()
        db.refresh(nuevo_producto)
        return nuevo_producto
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al crear producto: {str(e)}")

@app.get("/productos/", response_model=List[ProductoResponse])
def listar_productos(categoria_id: Optional[int] = None, db: Session = Depends(get_db)):
    try:
        query = db.query(Producto)
        if categoria_id:
            query = query.filter(Producto.categoria_id == categoria_id)
        return query.all()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al listar productos: {str(e)}")

@app.get("/productos/{producto_id}", response_model=ProductoResponse)
def obtener_producto(producto_id: int, db: Session = Depends(get_db)):
    try:
        producto = db.query(Producto).filter(Producto.id == producto_id).first()
        if not producto:
            raise HTTPException(status_code=404, detail="Producto no encontrado")
        return producto
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener producto: {str(e)}")

@app.put("/productos/{producto_id}", response_model=ProductoResponse)
def actualizar_producto(producto_id: int, producto: ProductoCreate, db: Session = Depends(get_db)):
    try:
        # Verificar si existe la categoría
        categoria = db.query(Categoria).filter(Categoria.id == producto.categoria_id).first()
        if not categoria:
            raise HTTPException(status_code=404, detail="La categoría especificada no existe")
            
        db_producto = db.query(Producto).filter(Producto.id == producto_id).first()
        if not db_producto:
            raise HTTPException(status_code=404, detail="Producto no encontrado")
        
        db_producto.nombre = producto.nombre
        db_producto.categoria_id = producto.categoria_id
        db_producto.precio = producto.precio
        db_producto.stock = producto.stock
        db_producto.url = producto.url
        
        db.commit()
        db.refresh(db_producto)
        return db_producto
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al actualizar producto: {str(e)}")

@app.delete("/productos/{producto_id}")
def eliminar_producto(producto_id: int, db: Session = Depends(get_db)):
    try:
        producto = db.query(Producto).filter(Producto.id == producto_id).first()
        if not producto:
            raise HTTPException(status_code=404, detail="Producto no encontrado")
        
        db.delete(producto)
        db.commit()
        return {"mensaje": "Producto eliminado correctamente"}
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Error al eliminar producto: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)