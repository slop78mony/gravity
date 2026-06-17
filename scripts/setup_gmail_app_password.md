# Cómo obtener la contraseña de aplicación de Gmail

Necesitas una **Contraseña de Aplicación** (no tu contraseña normal de Gmail).
Esto es necesario para que el script pueda enviarte emails de forma autónoma.

## Pasos

1. Ve a tu cuenta de Google: https://myaccount.google.com
2. Seguridad → "Verificación en dos pasos" → actívala si no está activa
3. Seguridad → busca "Contraseñas de aplicaciones"
4. En "Seleccionar app" elige "Otra (nombre personalizado)"
5. Escribe: `iPad Optimizer`
6. Clic en "Generar"
7. Copia la contraseña de 16 caracteres que aparece (ej: `abcd efgh ijkl mnop`)
8. Úsala en el comando con `--smtp-pass "abcd efgh ijkl mnop"` (sin espacios)

## Verificar que funciona

```bash
python scripts/auto_optimize.py \
  --path ~/Library/Mobile\ Documents \
  --email tu@gmail.com \
  --smtp-pass "abcdefghijklmnop" \
  --clean
```
