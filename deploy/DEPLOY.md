# Despliegue de SmartFlow en una máquina virtual de Azure

## 1. Crear la máquina virtual (Portal de Azure)
1. **Create a resource → Virtual machine**
2. Datos sugeridos:
   - Resource group: `rg-smartflow`
   - Name: `vm-smartflow`
   - Region: **Brazil South** (la misma del recurso de Computer Vision)
   - Image: **Ubuntu Server 24.04 LTS**
   - Size: **Standard_B1s** o **B2s** (B1s es suficiente para la demo)
   - Authentication: **SSH public key**, usuario `azureuser` (descarga el archivo `.pem`)
   - Inbound ports: **SSH (22)** y **HTTP (80)**; luego agrega una regla para el puerto **8080** (Networking → Add inbound port rule)
3. **Review + create → Create**. Copia la **IP pública**.

## 2. Conectarse
```bash
ssh -i vm-smartflow_key.pem azureuser@<IP_PUBLICA>
```
(En Windows, si da error de permisos del .pem: clic derecho → Propiedades → Seguridad → deja solo tu usuario.)

## 3. Instalar dependencias del sistema
```bash
sudo apt update && sudo apt install -y python3-venv python3-pip nginx git
```

## 4. Clonar el proyecto e instalar
```bash
cd ~
git clone https://github.com/Edmundo212/MoviAI.git
cd MoviAI
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env
nano .env        # pega VISION_ENDPOINT, VISION_KEY y (opcional) MONGODB_URI
```
Prueba rápida: `.venv/bin/python app.py` y abre `http://<IP_PUBLICA>:5000` (requiere abrir el puerto 5000; si no, pasa al paso 5). `Ctrl+C` para salir.

## 5. Servicio permanente (Gunicorn + systemd)
```bash
sudo cp deploy/smartflow.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now smartflow
sudo systemctl status smartflow      # debe decir "active (running)"
```
> Usar **1 worker** (`-w 1`): los análisis corren en hilos dentro del mismo proceso.

## 6. Nginx (puerto 8080)
SmartFlow se publica en el puerto **8080** para convivir con otros sitios en el puerto 80.
```bash
sudo cp deploy/nginx-smartflow.conf /etc/nginx/sites-available/smartflow
sudo ln -sf /etc/nginx/sites-available/smartflow /etc/nginx/sites-enabled/smartflow
sudo nginx -t && sudo systemctl reload nginx
```
En el portal de Azure: VM → **Networking** → **Add inbound port rule** → puerto **8080**, TCP, Allow.

Abre **http://<IP_PUBLICA>:8080/** — ¡listo! Verifica también `http://<IP_PUBLICA>:8080/salud`.

## 7. Actualizar después de cambios en GitHub
```bash
cd ~/MoviAI && git pull && .venv/bin/pip install -r requirements.txt && sudo systemctl restart smartflow
```

## Ver errores
```bash
sudo journalctl -u smartflow -n 100 --no-pager
```

## Costos (referencia)
- VM B1s: cubierta por los créditos de **Azure for Students**. **Apaga la VM** (Stop) cuando no la uses para no gastar créditos.
- Computer Vision F0: gratis (con límite mensual de llamadas).
