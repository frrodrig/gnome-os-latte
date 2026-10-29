# GNOME OS para Xiaomi Mi Pad 2

Primer prototipo de GNOME OS Preview 51 para probar desde un USB externo. No instala GNOME OS en la tablet y no modifica postmarketOS ni el eMMC.

Esta adaptación se basa en GNOME OS y BuildStream oficiales, no en Arch Linux. Fija GNOME Build Meta al commit `8a89846df11e86cee57c728a86a247e61d604b84` y el kernel de Xiaomi Mi Pad 2 (`xiaomi-latte-dev/linux_latte`) al commit `575dbb62ac89c5e3e49f98c386255178e29c9ec5`. Mantiene la arquitectura CPU x86-64 genérica: no activa `x86_64_v3`.

## Compilar

Se necesita Linux, Git, Python 3, GNU Make, GnuPG, BuildStream 2.6 o posterior y su entorno de sandbox requerido por GNOME OS, además de conexión a Internet y espacio libre para el checkout y la compilación completa de GNOME OS. Consulta también los requisitos de compilación de GNOME OS. En la raíz del proyecto:

```sh
bash build/build-usb.sh
```

El script mantiene el checkout GNOME temporal en `.build/` y deja `disk.iso` en `.build/out/`. BuildStream guarda su caché en la ubicación que tenga configurada (normalmente bajo `~/.cache/buildstream`). El script no recibe rutas a discos y no escribe en dispositivos de bloque.

Para esta imagen de prueba se generan las claves de prueba públicas (`snakeoil`) que recomienda GNOME para compilaciones locales. No proporcionan seguridad y no son claves privadas de este dispositivo; no las inscribas en el firmware. Si Secure Boot bloquea el medio, detente en vez de cambiar ajustes o inscribir claves.

**La imagen no está incluida en el repositorio.** Solo debe considerarse disponible si el comando de compilación termina correctamente y el archivo `.build/out/disk.iso` existe y no está vacío. El primer arranque en la tablet requiere validación manual.

## Compatibilidad y prueba USB

La imagen es x86-64 y requiere firmware UEFI capaz de arrancar una aplicación EFI x86-64. La Mi Pad 2 puede tener firmware UEFI de 32 bits aun con una CPU x86-64; no supongas que es compatible solo por ser originalmente un modelo Windows. Comprueba en postmarketOS, de forma no destructiva:

```sh
cat /sys/firmware/efi/fw_platform_size
```

El valor `64` es necesario para esta imagen. Si el archivo no existe o muestra `32`, no intentes arrancarla con este medio.

Para probar, escribe la imagen en un USB vacío con una herramienta de imágenes, revisando cuidadosamente el dispositivo de destino: escribir la imagen borra el contenido del USB. Arranca mediante el menú de arranque temporal del firmware. No selecciones instalar, reparar ni flashear el sistema. No cambies GPT, variables EFI, Secure Boot, el orden permanente de arranque ni el cargador interno. Si Secure Boot impide el arranque, detente; esta guía no autoriza a desactivarlo ni a inscribir claves. Si no arranca, apaga, retira el USB y vuelve a arrancar normalmente desde postmarketOS.

La configuración desactiva los servicios de actualización de imagen de GNOME OS para evitar que sustituyan el kernel Latte por uno genérico. No se distribuyen firmware binario ni perfiles UCM comunitarios: sus licencias de redistribución no están verificadas. Wi-Fi, Bluetooth, audio y cámaras pueden no funcionar, aunque el kernel incluya los controladores.

## Estado de soporte

GNOME OS Preview es experimental. No se ha verificado el arranque en hardware real ni el funcionamiento de pantalla táctil, rotación, suspensión, batería, Wi-Fi, audio o cámaras. La compilación de recetas no equivale a una imagen de arranque validada.
