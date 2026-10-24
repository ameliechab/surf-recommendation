# Interface

L'application Streamlit : lecture des scores, sélection des créneaux, explications et affichage. Specs détaillées dans l'onglet « Interface utilisateur » du [Google Doc](https://docs.google.com/document/d/1T4jo2obXOgmlyBt6aLAR7TgoMA6Z_V0V8MXFOUA-Q4s/edit), maquettes dans [Figma](https://www.figma.com/design/mRagf7nYUj9qZelxzkUze4).

## `app.py`, `selection.py`, `explain.py`, `ui.py`

Sections « Processus de recommandation » (étape recherche utilisateur), « Sélection », « Sorties » et onglet « Interface utilisateur » du doc. Maquette : Figma « FindYourWave – Maquettes interface », planche C v2.

| Étape | Ce que fait le code |
|---|---|
| Lecture | Clé **publishable** (rôle `anon`, lecture seule). `spot_hour_scores` du niveau choisi, `marine_forecast` et `surf_spot_properties` sur les jours demandés, page par page, gardés en cache 10 min. |
| Filtres | Distance à vol d'oiseau depuis une liste de villes ; date et heure converties de l'UTC vers Europe/Paris ; un créneau compte s'il se termine avant l'heure de fin choisie. |
| Sélection | Par spot et par jour : heure au meilleur score, étendue aux heures consécutives à moins de 10 points. Score minimum 50, 5 résultats au plus, à égalité le spot le plus proche. |
| Explication | Templates en français, sans IA. Phrase principale : les 2 plus fortes contributions (sous-score × poids) parmi les critères notés 50 ou plus, avec la raison s'ils ne sont que corrects, et « en bas / en haut de fourchette » pour une houle idéale proche d'une borne. Remarque (texte gris) pour tout autre sous-score de 50 à 69, point de vigilance (barre rose) sous 50 et pour le vent de mer s'il retire au moins 5 % du score. Le détail du score affiche les contributions et la pénalité de vent de mer : leur somme retombe sur le score global. |
| Houle affichée | Au large (prévision brute) et sur le spot (hauteur × facteur de direction) : c'est la hauteur sur le spot que le scoring compare aux seuils du niveau. |
| Absence de résultat | Raison principale par jour : aucun spot dans le rayon, pas de prévision, niveau, nuit ou horaires, houle trop faible ou trop forte, vent trop fort, conditions moyennes. |
| Fraîcheur | Date du dernier calcul (`scored_at`), bouton « Rafraîchir » (vide le cache, ne relance pas de collecte), alerte si les scores ont plus de 12 h. |
| Export | Bouton « Télécharger les résultats (CSV) » : une ligne par recommandation, avec sous-scores, houle au large et sur le spot, explication, remarques et vigilances. |
| Formulaire | Champs à clé fixe dans `st.session_state` : la recherche est prise en compte dès le premier clic. |

`selection.py` et `explain.py` sont du Python pur, testés sans Streamlit. Le module s'appelle `selection.py` et non `select.py`, car `select` est un module de la bibliothèque standard de Python.

[← Retour au README](../README.md)
