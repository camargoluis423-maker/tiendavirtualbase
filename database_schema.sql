-- =====================================================================
-- Esquema de Base de Datos para Tienda Virtual M&T · COM-1 (MariaDB / MySQL)
-- =====================================================================

CREATE DATABASE IF NOT EXISTS tienda_mt
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

USE tienda_mt;

-- 1. Tabla de Usuarios (Compradores y Vendedores)
CREATE TABLE IF NOT EXISTS usuarios (
    id INT AUTO_INCREMENT PRIMARY KEY,
    usuario VARCHAR(120) NOT NULL UNIQUE,
    alias VARCHAR(80) NOT NULL,
    nombre VARCHAR(120) NOT NULL,
    rol ENUM('comprador', 'vendedor') NOT NULL DEFAULT 'comprador',
    perfil VARCHAR(50) NOT NULL DEFAULT 'General',
    password_hash VARCHAR(255) NOT NULL,
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- 2. Tabla de Categorías
CREATE TABLE IF NOT EXISTS categorias (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(60) NOT NULL UNIQUE,
    color VARCHAR(20) NOT NULL DEFAULT '#ff0033'
) ENGINE=InnoDB;

-- 3. Tabla de Productos (Catálogo con imágenes)
CREATE TABLE IF NOT EXISTS productos (
    id INT AUTO_INCREMENT PRIMARY KEY,
    nombre VARCHAR(160) NOT NULL,
    categoria VARCHAR(60) NOT NULL,
    precio DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    stock INT NOT NULL DEFAULT 0,
    foto VARCHAR(255) DEFAULT '',
    especs VARCHAR(255) DEFAULT '',
    actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- 4. Tabla de Pedidos (Compras y órdenes)
CREATE TABLE IF NOT EXISTS pedidos (
    id INT AUTO_INCREMENT PRIMARY KEY,
    fecha DATETIME NOT NULL,
    cliente VARCHAR(120) NOT NULL,
    usuario VARCHAR(120) DEFAULT NULL,
    perfil VARCHAR(50) NOT NULL DEFAULT 'General',
    pago VARCHAR(50) NOT NULL,
    subtotal DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    descuento DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    iva DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    total DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    estado ENUM('Pendiente', 'Preparando', 'Enviado', 'Entregado', 'Cancelado') NOT NULL DEFAULT 'Pendiente',
    stock_reintegrado BOOLEAN NOT NULL DEFAULT FALSE,
    datos_pago_json TEXT DEFAULT NULL,
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- 5. Tabla de Detalle de Pedido (Items comprados)
CREATE TABLE IF NOT EXISTS pedido_items (
    id INT AUTO_INCREMENT PRIMARY KEY,
    pedido_id INT NOT NULL,
    producto_id INT NOT NULL,
    nombre VARCHAR(160) NOT NULL,
    categoria VARCHAR(60) NOT NULL,
    cantidad INT NOT NULL,
    precio DECIMAL(10,2) NOT NULL,
    importe DECIMAL(10,2) NOT NULL,
    FOREIGN KEY (pedido_id) REFERENCES pedidos(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------
-- Datos Semilla Iniciales (Categorías)
-- ---------------------------------------------------------------------
INSERT IGNORE INTO categorias (nombre, color) VALUES
('Computadoras', '#00b4d8'),
('Compus Gaming', '#ff0033'),
('Componentes', '#ff4d00'),
('Equipo', '#00f0ff'),
('Software', '#9d4edd'),
('Mobiliario', '#ffaa00');
