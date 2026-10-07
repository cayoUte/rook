# Aula5: página 3D para el QR

- index.html: la app completa en un solo archivo.
- og.png: la imagen que aparece al compartir el enlace.

## Antes de imprimir las tarjetas

1. Abre index.html con un editor de texto y busca TU-INVITACION. Cámbialo por tu invitación permanente de Discord (Invitar > Editar enlace > Nunca expira).
2. Para activar el botón de WhatsApp, busca "whatsapp":"" y pon tu número con código de país, solo dígitos, por ejemplo "593991234567".

## Videos de cada taller

Cada taller tiene un campo "video" vacío en el bloque de datos de index.html. Mientras esté vacío, la hoja del taller no muestra nada.

1. Sube el video a YouTube, como Short o como video "No listado".
2. Busca el taller por su id, por ejemplo "id": "github", y pega el enlace en su "video":
   - Video vertical (Short): "video": "https://youtube.com/shorts/ABCDEFGHIJK"
   - Video horizontal: "video": "https://youtu.be/ABCDEFGHIJK"
3. Guarda y sube index.html.

Si el enlace es de un Short, el reproductor sale vertical. Cualquier otro enlace de YouTube sale horizontal.

Para que la página no se trabe:

- La hoja muestra solo la miniatura del video. YouTube se carga cuando alguien la toca.
- Mientras el video está abierto, la torre 3D se detiene. Vuelve a moverse al cerrar la hoja o pasar a otro taller.
- Al cerrar la hoja o pasar a otro taller, el reproductor se borra y el video deja de sonar.

## Publicarla gratis en GitHub Pages

1. Crea un repositorio público, por ejemplo aula5.
2. Sube index.html y og.png a la raíz del repositorio.
3. Ve a Settings > Pages > Deploy from a branch > main / (root) > Save.
4. En unos minutos queda en https://TU-USUARIO.github.io/aula5/. Ese es el enlace del QR.
5. Para que WhatsApp muestre la imagen al compartir, cambia content="og.png" por https://TU-USUARIO.github.io/aula5/og.png.

## Enlaces directos

Agrega un ancla al final del enlace para abrir un taller o una ruta, útil para tarjetas o afiches de un taller específico:

#github · #html · #logica · #poo · #fastapi · #botpy · #pandas · #grafos · #react · #fpjs · #express · #ts · #javamod · #patrones · #junit · #sql · #mongo · #optim · #ia · #next · #realtime · #movil · #spring · #rabbit · #oauth · #linux · #docker · #cicd · #seguridad · #integracion · #r-fundamentos · #r-python · #r-js · #r-java · #r-devops · #r-algoritmos
