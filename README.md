# Plantilla LaTeX para elaborar la memoria del Trabajo de Fin de Grado (de la ETSII URJC)

Este repositorio contiene una plantilla para que los alumnos puedan crear la memoria de su Trabajo de Fin de Grado (TFG) usando LaTeX. LaTeX es un sistema de composición de textos para crear documentos muy usado por los científicos para elaborar artículos de investigación y otros documentos.

Puedes ver el PDF resultante de la plantilla en el [repo de GitHub](https://github.com/codeurjc-students/tfg-template/blob/master/tfg.pdf) o [descargar el PDF](https://github.com/codeurjc-students/tfg-template/raw/refs/heads/master/tfg.pdf).

Aunque esta plantilla puede usarse para crear cualquier tipo de TFG, tiene una estructura de capítulos y subcapítulos diseñada específicamente para los TFGs orientados a la implementación de una aplicación web.

El grupo docente de Aplicaciones Web y Calidad del Software de la Escuela Técnica Superior de Ingeniería Informática (ETSII) de la Universidad Rey Juan Carlos (URJC) tiene una guía detallada para realizar TFGs orientados a la implementación de una aplicación web. Al seguir los pasos definidos en esa guía se va elaborando gran parte de la memoria a medida que se realiza el trabajo.

Este grupo docente está formado por por Micael Gallego, Michel Maes, Óscar Soto e Iván Chicano.

## ¿Cómo crear la memoria en LaTeX?

Para facilitar la revisión del tutor el alumno deberá editar la memoria usando el editor online [Overleaf](https://www.overleaf.com/) con una cuenta gratuita. No obstante, si por algún motivo se desea editar el documento en local, se proporcionan las instrucciones más abajo.

### Edición de la memoria online con Overleaf

El tutor creará un proyecto nuevo en Overleaf que contendrá esta plantilla. Pasará la URL al alumno para que pueda comenzar con su edición.

### Edición de la memoria en local

En caso de querer trabajar de manera local, es necesario instalar un editor con ayuda a la edición de LaTeX y el compilador de LaTeX.

#### Instalación del editor de Latex

Se recomienda utilizar [VSCode](https://code.visualstudio.com/) haciendo uso de la extensión [LaTeX Workshop](https://marketplace.visualstudio.com/items?itemName=James-Yu.latex-workshop).

> TIP: Si quieres que los ficheros `.tex` tengan el world wrap activado por defecto cuando los abras, añade esta preferencia (F1 → Preferences: Open User Settings (JSON)):
```
"[latex]": {
    "editor.wordWrap": "on"
}
```

#### Uso de Latex con Docker (recomendado)

1. Instala [Docker](https://www.docker.com/).

2. Instala la extensión VSCode [Dev Containers](https://marketplace.visualstudio.com/items?itemName=ms-vscode-remote.remote-containers)

3. Abre este repositorio en VSCode

4. Reabre el repositorio en un contenedor ejecutando `Dev Containers: Reopen in Container` en la paleta de comandos de VSCode. Ojo que este comando descargará la imagen `codeurjc/tfg-latex` que ocupa 4.78GB.

NOTA: Las operaciones git dentro del contenedor no funcionan correctamente. Está pendiente de solucionar estos problemas para que funcione bien:
   * Obtener las clases de git del host
   * Ejecutar el contenedor con los permisos del usuario para que los ficheros no sean de root

#### Instalación nativa de LaTeX (no recomendado)

La instalación nativa es menos portable y puede tener problemas de incompatibilidades con tu sistema. No obstante, lo puedes necesitar por eficiencia o por otros motivos.

Aunque hay muchas distribuciones de LaTeX, se recomienda instalar [TexLive](https://www.tug.org/texlive/):

* [Instalar en Linux](https://www.tug.org/texlive/quickinstall.html)
* [Instalar en Windows](https://www.tug.org/texlive/windows.html)
* [Instalar en MacOS](https://www.tug.org/mactex/)

## Diferencias de esta plantilla respecto a la plantilla oficial de la ETSII

Esta plantilla se ha creado partiendo de la versión original creada por los profesores de la Universidad Rey Juan Carlos Manuel Rubio Sánchez y Clara Simón de Blas.

Respecto a la plantilla oficial, se han añadido nuevas funcionalidades, así como documentación y una nueva propuesta de estructura:

* El documento `tfg.tex` ahora referencia a distintas páginas de la carpeta `/pages` para facilitar la navegación por el documento (que tiene una extensión considerable).
* Se utiliza una estructura del documento específica de los trabajos con temática web que han sido desarrollados con la metodología propuesta por los profesores Micael Gallego, Michel Maes, Óscar Soto e Iván Chicano.
* Se ha movido la configuración del documento a un archivo aparte (`config.tex`) para facilitar su modificación y abstraer detalles técnicos.
* Se añade una macro para que el profesor y el alumno puedan incluir comentarios que claramente se diferencian del contenido del documento.
* Se han actualizado algunos paquetes LaTeX para ampliar las opciones de configuración:
  * `color` -> `xcolor`
* Se añaden ejemplos avanzados de cómo incluir código fuente con resaltado de sintaxis usando el paquete `listings`.
