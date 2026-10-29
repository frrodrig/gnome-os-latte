# Compilar y probar desde USB

## Requisitos

Usa una distribución Linux o WSL2 con una distribución Linux funcional, Git, Python 3, GNU Make, GnuPG, BuildStream 2.6 o posterior y las dependencias de sandbox exigidas por GNOME OS. El build oficial de GNOME OS puede tardar y requiere conexión a Internet, almacenamiento amplio y herramientas de compilación compatibles con BuildStream. No instales herramientas ni cambies la configuración del host sin autorización.

## Compilación

Desde la raíz del repositorio:

```sh
bash build/build-usb.sh
```

El script:

1. Clona GNOME Build Meta dentro de `.build/`, fija el commit GNOME OS Preview 51 y comprueba el SHA.
2. Modifica el checkout temporal para reemplazar el kernel genérico por el kernel de Latte, añadir la configuración específica de la tablet y omitir las actualizaciones de imagen incompatibles.
3. Genera en ese checkout las claves públicas de prueba `snakeoil` requeridas por GNOME OS; no son claves seguras para uso personal ni deben inscribirse en el firmware.
4. Ejecuta BuildStream para `x86_64`, canal `stable`, con un máximo predeterminado de dos tareas simultáneas (`BST_MAX_JOBS` permite ajustarlo).
5. Extrae el elemento oficial `gnomeos/live-image.bst` en `.build/out/`.

La revisión del kernel también está fijada. Las dependencias transitivas y el junction de Freedesktop SDK son los definidos por el commit fijado de GNOME Build Meta. BuildStream almacena sus fuentes y artefactos en su caché configurada, habitualmente fuera de `.build/`.

No uses una ruta de disco como argumento del script. Este solo escribe dentro de `.build/`. Si la compilación falla, no se ha generado una imagen utilizable.

## Comprobaciones antes de probar

Desde postmarketOS, consulta el modo UEFI sin modificar el dispositivo:

```sh
cat /sys/firmware/efi/fw_platform_size
uname -m
```

La imagen requiere una CPU x86-64 y UEFI de 64 bits. `fw_platform_size` debe devolver `64`. La ausencia del archivo no confirma que el firmware sea x86-64; si el valor es `32` o no puedes confirmarlo, detente y no arranques esta imagen.

Confirma que `.build/out/disk.iso` existe y tiene tamaño distinto de cero. Solo después, escríbela en un USB vacío con una herramienta de imágenes; escribirla borra el contenido del USB. Comprueba el nombre del dispositivo de destino varias veces. No selecciones el almacenamiento interno de la tablet ni ejecutes comandos para flashear el eMMC.

No cambies Secure Boot, inscribas claves ni modifiques variables EFI como parte de esta prueba. Si Secure Boot impide el arranque, detente y solicita autorización antes de cualquier cambio en firmware. Selecciona el USB desde el menú de arranque temporal y no elijas ninguna opción de instalación, reparación o actualización permanente.

## Recuperación y limitaciones

Si el medio no arranca o algo falla, apaga la tablet, desconecta el USB y arráncala normalmente. El procedimiento no cambia el disco interno ni el cargador; no debería requerir recuperación del sistema interno.

El kernel incluye soporte de hardware de Latte, el mapeo de los botones capacitivos y la carga del módulo de audio RT5659. No se copian `BCM4356A2.hcd`, `shisp_2401a0_v21.bin`, el archivo de calibración Wi-Fi ni los perfiles ALSA UCM de los repositorios comunitarios: no se ha verificado que sus licencias permitan redistribuirlos. La imagen puede arrancar, pero funciones específicas pueden no estar disponibles.

No se ha probado aún el arranque en una Mi Pad 2 física. Deben probarse el táctil, rotación, suspensión, batería, inalámbrico, audio y cámaras; no se debe inferir soporte funcional solo porque la receta del kernel compile.
