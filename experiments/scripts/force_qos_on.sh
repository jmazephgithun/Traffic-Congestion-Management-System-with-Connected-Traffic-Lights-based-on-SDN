#!/bin/bash
# Force la QoS ON dans Ryu sans avoir besoin de SUMO/orchestrateur
# Envoie un busy=20 (bien au-dessus du seuil de 8.0)
# Utile pour tester le reseau independamment de SUMO

echo "Envoi de busy=20 a Ryu pour activer la QoS..."
curl -s -X POST http://localhost:8080/metrics \
    -H "Content-Type: application/json" \
    -d '{"busy": 20, "ns_q": 10, "ew_q": 10}'

echo ""
echo ""
echo "Verification:"
curl -s http://localhost:8080/health
echo ""
echo ""
echo "Si priority_enabled=true -> QoS activee"
echo "Verifier les regles OVS:"
echo "  sudo ovs-ofctl -O OpenFlow13 dump-flows ap1 | grep set_queue"
