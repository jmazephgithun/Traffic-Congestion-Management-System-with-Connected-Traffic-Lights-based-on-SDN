# Bureau distant exposant sumo-gui, l'interface graphique reelle de SUMO,
# dans un navigateur via noVNC. Reutilise l'image du banc pour avoir SUMO
# et le reseau du projet a l'identique.
FROM memoire3-experiment:local

USER root
RUN apt-get update && apt-get install -y --no-install-recommends \
    xvfb x11vnc novnc websockify fluxbox \
    libgl1-mesa-dri libglx-mesa0 mesa-utils \
    && rm -rf /var/lib/apt/lists/*

COPY docker/gui/start.sh /usr/local/bin/start-gui.sh
RUN chmod +x /usr/local/bin/start-gui.sh

EXPOSE 6080
ENTRYPOINT ["/usr/local/bin/start-gui.sh"]
