# Plantilla para la memoria del TFG

En este repositorio se establece un formato de plantilla para memorias de Trabajos de Fin de Grado de la Escuela Técnica Superior de Ingeniería Informática (Universidad Rey Juan Carlos), una versión revisada y extendida de la versión original creada por los profesores de la URJC Manuel Rubio Sánchez y Clara Simón de Blas.

## Trabajar con LaTeX

### Instalación de LaTeX

Para trabajar con LaTeX es necesario instalar una distribución de LaTeX (se recomienda [TeX Live](https://www.tug.org/texlive/))

* [Instalar en Linux](https://www.tug.org/texlive/quickinstall.html)
* [Instalar en Windows](https://www.tug.org/texlive/windows.html)
* [Instalar en MacOS](https://www.tug.org/mactex/)

### Instalación del IDE + Plugins

Para editar la memoria, se recomienda utilizar [VSCode](https://code.visualstudio.com/) haciendo uso de las siguientes extensiones: 

* [LaTeX Workshop](https://marketplace.visualstudio.com/items?itemName=James-Yu.latex-workshop)
* [LaTeX language support](https://marketplace.visualstudio.com/items?itemName=torn4dom4n.latex-support)

#### Instalación con Docker (opcional)

Haciendo uso de la extensión _LaTeX Workshop_ también es posible dockerizar todos los paquetes LaTeX:

1. Teniendo [Docker](https://www.docker.com/) instalado, descargamos una imagen que contenga los paquetes LaTeX:

```
$ docker pull tianon/latex
```

2. Abrir el archivo _settings.json_ de VSCode (Ctrl + Shift + P > Preferences: Open Settings) y añadir las siguientes lineas:

```
{
    "latex-workshop.docker.enabled": true,
    "latex-workshop.latex.outDir": "./out",
    "latex-workshop.synctex.afterBuild.enabled": true,
    "latex-workshop.view.pdf.viewer": "tab",
    "latex-workshop.docker.image.latex": "tianon/latex",
}
```

Los archivos resultantes estarán situados en la carpeta `out/`

## Diferencias respecto a la plantilla oficial

Respecto a la plantilla oficial, se han añadido nuevas funcionalidades, así como documentación y una nueva propuesta de estructura:

* Se incluye documentación sobre la instalación de LaTeX y los plugins para trabajar en un IDE (VSCode).
  * Se incluye la carpeta _.vscode/_ con la configuración necesario para no mostrar ficheros intermedios de compilación
  * Propuesta para trabajar con contenedores Docker
* El documento _tfg.tex_ ahora referencia a distintas páginas de la carpeta _pages/_ para facilitar la navegación.
* Se añade una macro para comentar apropiadamente el PDF final, con el fin de que alumno y profesor puedan dejar retroalimentación de manera sencilla en cualquier sección utilizando `\tutor{Un comentario}` o `\alumno{Otro comentario}`
* Se han actualizado algunos paquetes LaTeX para ampliar las opciones de configuración:
  * `color` -> `xcolor`