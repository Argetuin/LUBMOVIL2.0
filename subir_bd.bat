@echo off
echo ==========================================
echo   SINCRONIZANDO BASE DE DATOS LUBMOVIL
echo ==========================================
echo.

echo 1. Preparando archivo...
git add lubmovil.db

echo 2. Guardando cambios localmente...
git commit -m "Sincronizacion automatica de base de datos desde script local"

echo 3. Subiendo a GitHub (esto activara Render)...
git push origin master

echo.
echo ==========================================
echo   PROCESO COMPLETADO EXITOSAMENTE
echo ==========================================
echo.
pause
