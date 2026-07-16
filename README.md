# Fée Mazine — Pilote de pointage des passages

Pilote local pour remplacer la retranscription manuelle papier → Excel des
passages au LAEP. Le système propose deux modes de pointage :

- **Mode anonyme** (par défaut) : chaque passage est une ligne indépendante
  sans aucune donnée identifiante (pas de nom, prénom, ni identifiant).
- **Mode carte pseudonyme** (optionnel) : un code pseudonyme unique (ex.
  `H9V4-K7Q2-PF31`) est attribué à une famille pour permettre un comptage
  certifié de familles distinctes, sans jamais collecter de nom ou de donnée
  d'identité directe. Le mode carte reste strictement optionnel : une famille
  qui refuse la carte continue d'être comptée via le mode anonyme, sans
  aucune dégradation de service.

## Installation

1. Créer et activer un environnement virtuel (optionnel mais recommandé) :

   ```
   python -m venv venv
   venv\Scripts\activate
   ```

2. Installer les dépendances :

   ```
   pip install -r requirements.txt
   ```

## Lancer le projet

**Le plus simple** : double-cliquer sur `lancer.bat`. Une fenêtre s'ouvre et
affiche les journaux du serveur — la laisser ouverte tant que l'appli est
utilisée. Pour arrêter, double-cliquer sur `arreter.bat` (ou fermer
simplement la fenêtre de `lancer.bat`).

En ligne de commande, depuis le dossier `fee-mazine-pilot` :

```
venv\Scripts\activate
uvicorn app:app
```

(`lancer.bat` ne passe pas `--reload` : ce mode surveillance de fichiers ne
sert qu'en développement, quand on modifie le code au fil de l'eau — pas
au quotidien pour l'association. Pour développer, ajouter `--reload`
manuellement à cette dernière commande.)

Ouvrir ensuite dans un navigateur : http://127.0.0.1:8000

Le fichier `data/passages.xlsx` est créé automatiquement au premier
enregistrement (avec la feuille "Passages" et les en-têtes de colonnes).
Il ne doit pas être versionné (voir `.gitignore`).

## Fonctionnalités

- **Pointage** (page d'accueil) : saisie rapide d'un passage (adultes,
  enfants, nouvelle famille), avec un résumé du nombre de passages
  aujourd'hui / cette semaine / ce mois / cette année.
- **Statistiques** : totaux (passages, adultes, enfants, personnes),
  répartition des réponses "nouvelle famille", et détail par année, mois,
  semaine et jour, avec un filtre par plage de dates.
- **Ouvrir le fichier Excel** : ouvre `data/passages.xlsx` dans l'application
  associée (Excel) sur le poste où tourne le serveur.
- **Exporter** : télécharge une copie horodatée du fichier Excel, utile pour
  le bilan CAF.
- **Importer** : remplace le fichier de passages par un fichier Excel
  importé. Le fichier doit contenir une feuille "Passages" avec exactement
  les colonnes Date, Heure, Adultes, Enfants, Nouvelle famille — tout autre
  format est refusé, pour ne jamais introduire de champ identifiant. Une
  sauvegarde du fichier remplacé est conservée dans `data/backups/`.
- **Partager avec l'équipe** : envoie le fichier par email ou vers Google
  Drive (voir configuration ci-dessous).
- **Informations** : dates de dernière modification, dernier export et
  dernier partage, affichées sur la page d'accueil.
- **Cartes pseudonymes** (onglet "Cartes") : attribution et gestion des
  cartes famille. Chaque carte porte un code pseudonyme unique généré
  aléatoirement (module `secrets`, jamais `random`). La fiche carte
  enregistre le nombre d'adultes et les enfants (date de naissance ou
  tranche d'âge déclarée). Aucun nom n'est demandé ni stocké.
- **Passage avec carte** : sur la page d'accueil, "Scanner une carte"
  permet d'enregistrer un passage en saisissant le code. Les compteurs
  (adultes, enfants) sont dupliqués automatiquement depuis la fiche carte,
  et "nouvelle famille" est déterminé automatiquement (oui si c'est le
  premier passage pour cette carte, non sinon).
- **Purge automatique** : les cartes sans passage depuis plus de N mois
  (12 par défaut, réglable) sont désactivées au démarrage du serveur.
  Les enfants associés sont supprimés mais les passages historiques sont
  conservés.
- **Heures** : module séparé de suivi du temps de l'équipe (voir section
  dédiée ci-dessous) — sans rapport avec l'anonymat du pointage LAEP.
- **Bilan CAF** (onglet "Bilan CAF") : préparation de la déclaration
  annuelle CAF en trois volets — heures d'activité par type CAF, 
  fréquentation annuelle (dérivée des passages existants), et fiche
  d'identité de la structure. Les heures d'organisation et de
  fonctionnement ne sont jamais stockées, uniquement calculées à
  l'affichage. Voir section dédiée ci-dessous.

Si `data/passages.xlsx` est ouvert dans Excel (ou une autre application) au
moment de valider un passage ou d'importer un fichier, l'application
affiche un message demandant de fermer le fichier avant de réessayer.

## Configurer le partage (email / Google Drive)

Le partage n'est pas configuré par défaut. Cliquer sur "Par email" ou
"Vers Google Drive" sur la page d'accueil ouvre automatiquement une popup
de réglages tant que ce moyen de partage n'est pas configuré (les boutons
"Réglages email" / "Réglages Drive" permettent de rouvrir cette popup à
tout moment, y compris pour modifier des réglages déjà enregistrés) :

- **Email** : serveur SMTP, port, adresse d'envoi, mot de passe (utiliser
  un mot de passe d'application, jamais le mot de passe principal du
  compte) et destinataires. Une fois enregistrés, le fichier est envoyé
  immédiatement.
- **Google Drive** : identifiant du dossier cible et identifiants du
  compte de service (JSON). L'envoi effectif vers Google Drive n'est pas
  encore implémenté dans ce pilote (nécessite l'ajout d'une bibliothèque
  cliente Google) : ces réglages préparent l'intégration future.

Ces paramètres sont enregistrés localement dans `data/parametres.json`
(ignoré par git, voir `.gitignore`) : ils ne sont jamais versionnés, et le
mot de passe / les identifiants déjà enregistrés ne sont jamais réaffichés
en clair dans les formulaires (laisser le champ vide en modifiant d'autres
réglages conserve la valeur existante).

## Cartes pseudonymes

### Principe

Les cartes sont un identifiant **pseudonyme** (pas anonyme) : elles
permettent de relier plusieurs passages à la même carte, c'est leur but.
Le code de la carte est généré avec un générateur cryptographiquement
aléatoire (`secrets`), au format `XXXX-XXXX-XXXX` (alphabet réduit sans
O/0/I/1/L pour éviter les confusions à la saisie manuelle). Aucune donnée
d'identité directe (nom, prénom) n'est demandée ni stockée.

Les données des cartes sont dans `data/cartes.db` (SQLite, jamais
versionnée). Les passages restent dans `data/passages.xlsx` avec deux
colonnes supplémentaires : Mode ("carte" ou "anonyme") et Carte (le code,
si mode carte). Les fichiers Excel au format 5 colonnes (ancien) sont
migrés automatiquement à l'ouverture.

### Comment attribuer une carte

1. Onglet "Cartes" → "Attribuer une nouvelle carte".
2. Indiquer le nombre d'adultes dans le foyer.
3. Ajouter chaque enfant avec sa date de naissance (préférée, pour un
   calcul dynamique de tranche d'âge) ou, à défaut, une tranche déclarée
   ("0-3" ou "4-6").
4. Cliquer "Générer la carte" → le code s'affiche pour impression ou
   plastification. Il ne sera plus affiché par la suite.

### Comment enregistrer un passage avec carte

1. Sur la page d'accueil (Pointage), cliquer "Scanner une carte".
2. Saisir le code de la carte.
3. Le passage est enregistré immédiatement. Les compteurs (adultes,
   enfants) sont dupliqués depuis la fiche carte — pas de saisie manuelle.
   "Nouvelle famille" est déterminé automatiquement (oui au premier
   passage, non ensuite). Si le code est inconnu, un message d'erreur
   propose de corriger la saisie ou d'attribuer une nouvelle carte.

### Comment modifier une fiche carte

1. Onglet "Cartes" → "Modifier une fiche carte".
2. Saisir le code de la carte.
3. Modifier le nombre d'adultes et/ou les enfants.
4. Les passages déjà enregistrés ne sont pas affectés (ils ont été
   dupliqués au moment de l'enregistrement).

### Limites du comptage — à documenter face à la CAF

**Familles différentes** : le nombre de "familles différentes" sur une
période combine les cartes distinctes ayant enregistré au moins un passage
(comptage exact) et les familles comptées en mode anonyme (approximation
déclarative, comme aujourd'hui). Ce chiffre ne garantit pas un décompte
exact car les familles sans carte ne peuvent pas être dédupliquées.

**Parents différents** : le nombre de "parents différents" additionne le
`nb_adultes` déclaré par carte active sur la période, sans distinguer si
c'est le même parent ou l'autre qui se présente d'une visite à l'autre.
C'est une approximation par excès.

**Nouvelles familles** : en mode carte, "nouvelle famille" est exact
(premier passage de la carte = oui). En mode anonyme, c'est une
déclaration manuelle qui peut être inexacte.

**Tranches d'âge** : si une date de naissance est disponible, la tranche
est calculée dynamiquement à la date du calcul (un enfant qui fête ses
4 ans change de tranche automatiquement). Si seule une tranche déclarée
est enregistrée, elle reste fixe.

## Module Heures (suivi du temps de l'équipe)

Un onglet "Heures" séparé du pointage des familles : suivi des horaires de
l'équipe (salariés/bénévoles), avec déclaration individuelle, validation
par les pairs, et statistiques de présence et de rémunération. Ce module
gère des données nominatives (noms, emails, salaires) — sans rapport avec
l'anonymat du pointage LAEP — stockées à part, dans `data/heures.db`
(SQLite, jamais versionnée).

**Connexion sans mot de passe** : un membre saisit son email sur
`/heures/connexion` et reçoit un lien de connexion à usage unique, valable
15 minutes. Si l'email est inconnu, l'appli propose de créer un profil
(nom + email) avant l'envoi du lien. Le tout premier membre créé sur une
base vide devient automatiquement administrateur (sinon personne ne
pourrait jamais accéder à l'espace admin).

**Envoi d'email** (lien de connexion) configuré par variables
d'environnement. Le plus simple : copier `.env.example` en `.env` puis
renseigner les valeurs :

```
copy .env.example .env
```

```
HEURES_SMTP_SERVEUR=smtp.gmail.com
HEURES_SMTP_PORT=587
HEURES_SMTP_UTILISATEUR=votre-compte@gmail.com
HEURES_SMTP_MOT_DE_PASSE=xxxx xxxx xxxx xxxx
HEURES_EMAIL_EXPEDITEUR=votre-compte@gmail.com
```

Le fichier `.env` est chargé automatiquement au démarrage du serveur
(voir `env_loader.py`) et n'est jamais versionné (voir `.gitignore`) :
c'est là que vont les identifiants réels. Pour Gmail, `HEURES_SMTP_MOT_DE_PASSE`
doit être un [mot de passe d'application](https://myaccount.google.com/apppasswords),
jamais le mot de passe principal du compte.

Si `.env` n'existe pas ou que ces variables ne sont pas définies, le lien
de connexion est affiché dans la console du serveur au lieu d'être envoyé
par email — pratique pour tester le module sans serveur SMTP réel.

**Règles clés** :
- Un horaire déclaré peut être corrigé pendant 48h après sa déclaration
  initiale, jamais après, et jamais une fois validé. Corriger un horaire
  qui a déjà reçu des validations partielles les annule (il faut à nouveau
  atteindre le seuil).
- Un membre ne peut jamais valider ses propres horaires. Dès qu'un horaire
  atteint le seuil de validations distinctes (réglable par un admin,
  2 par défaut), il passe définitivement au statut "validé".
- Le taux horaire moyen (salaire applicable ce mois-ci ÷ heures validées ce
  mois-ci) n'est visible que par le membre concerné et les administrateurs
  — jamais par les autres membres, y compris dans la vue équipe.
- Les salaires sont un historique (nouvelle ligne à chaque changement, avec
  une date d'effet) : aucune ligne existante n'est jamais modifiée.

## Logo

Le fichier `static/logo.svg` est une reconstitution du logo de l'association
à partir de l'image fournie (les couleurs de la charte — orange, rose,
vert anis — sont reprises dans toute l'interface via `static/style.css`).
Pour utiliser le fichier original, le remplacer par `static/logo.svg` (ou
adapter la balise `<img>` dans `templates/base.html` vers un autre format,
par ex. `logo.png`).

## Scénario de test manuel

### Pointage

1. Lancer le serveur (`uvicorn app:app --reload`) et ouvrir
   http://127.0.0.1:8000 dans le navigateur.
2. Cliquer sur "Valider ce passage" sans toucher aux compteurs (0 adulte,
   0 enfant) → un message d'erreur doit s'afficher et aucune ligne ne doit
   être ajoutée dans `data/passages.xlsx`.
3. Cliquer une fois sur le "+" du compteur "Adultes présents" (valeur : 1)
   et deux fois sur le "+" du compteur "Enfants présents" (valeur : 2).
4. Laisser "Nouvelle famille aujourd'hui" sur "Non renseigné" (valeur par
   défaut), puis cliquer sur "Valider ce passage".
5. Un message de confirmation doit s'afficher, les compteurs doivent être
   revenus à 0, et la carte "Aujourd'hui" doit afficher 1.
6. Ouvrir `data/passages.xlsx` (ou cliquer sur "Ouvrir le fichier Excel")
   pour vérifier qu'une nouvelle ligne est présente à la suite des lignes
   existantes, avec la date et l'heure du jour, 1 adulte, 2 enfants, et
   "Non renseigné".
7. Recommencer un passage en choisissant "Oui" pour "Nouvelle famille
   aujourd'hui" et vérifier que la colonne correspondante contient bien
   "Oui" sur la nouvelle ligne, sans avoir modifié les lignes précédentes.

### Statistiques

8. Aller sur "Statistiques" et vérifier que les totaux (passages, adultes,
   enfants, personnes) correspondent aux passages saisis à l'étape
   précédente, et que le tableau "Nouvelles familles" compte bien 1 "Oui"
   et 1 "Non renseigné".
9. Filtrer avec une plage de dates n'incluant pas aujourd'hui (ex. le mois
   dernier) et vérifier que tous les totaux passent à 0.

### Export / Import

10. Cliquer sur "Exporter le fichier Excel" : un fichier
    `passages_export_AAAA-MM-JJ.xlsx` doit se télécharger, avec le même
    contenu que `data/passages.xlsx`.
11. Aller sur "Importer", sélectionner un fichier Excel valide (par exemple
    le fichier exporté à l'étape précédente), cocher la case de
    confirmation et valider → une sauvegarde doit apparaître dans
    `data/backups/`, et les statistiques doivent refléter le fichier
    importé.
12. Essayer d'importer un fichier Excel dont les colonnes ne correspondent
    pas (par exemple un fichier vide ou avec d'autres en-têtes) → un
    message d'erreur doit s'afficher et `data/passages.xlsx` ne doit pas
    être modifié.

### Partage et informations

13. Sur la page d'accueil, vérifier que la ligne "Dernière modification"
    correspond à l'heure du dernier passage enregistré, et que "Dernier
    export" correspond à l'heure de l'étape 10.
14. Cliquer sur "Par email" (ou "Vers Google Drive") avant toute
    configuration → une popup de réglages s'ouvre automatiquement, au lieu
    d'un message d'erreur brut.
15. Remplir la popup email avec un compte valide (ex. Gmail avec un mot de
    passe d'application) et cliquer sur "Enregistrer et envoyer" →
    l'équipe reçoit un email avec le fichier en pièce jointe, et "Dernier
    partage" se met à jour sur la page d'accueil.
16. Rouvrir la popup via "Réglages email" : le mot de passe ne doit pas
    réapparaître en clair (champ vide avec une mention "déjà renseigné").
    Modifier uniquement les destinataires et enregistrer → vérifier que le
    mot de passe existant a bien été conservé (l'envoi doit continuer à
    fonctionner sans avoir eu à le ressaisir).

### Heures — de bout en bout (deux comptes de test)

Sans `HEURES_SMTP_*` configuré, le lien de connexion apparaît dans la
console du serveur (`[heures] SMTP non configuré — lien de connexion
pour ... : http://...`) : pas besoin d'une vraie boîte mail pour ce test.

17. Aller sur l'onglet "Heures" → "Connexion", saisir un premier email
    (ex. `admin@test.fr`) → l'appli propose de créer un profil (nom +
    email) puisqu'il n'existe pas encore.
18. Créer le profil, récupérer le lien de connexion dans la console du
    serveur et l'ouvrir dans le navigateur → redirection vers "Mon
    espace", connecté. Un onglet "Admin" doit apparaître dans la
    sous-navigation : ce premier compte est automatiquement administrateur.
19. Se déconnecter, recommencer les étapes 17-18 avec un deuxième email
    (ex. `membre@test.fr`) → ce second compte est un membre normal (pas
    d'onglet "Admin").
20. Avec le compte membre, déclarer un horaire du jour (arrivée/départ) →
    confirmation, l'horaire apparaît dans "Mes horaires" avec le statut
    "Déclaré (0/2)".
21. Toujours avec le compte membre, essayer de valider son propre horaire
    (en interrogeant directement `/heures/valider/<id>`) → doit être
    refusé. Se reconnecter avec le compte admin : l'horaire du membre doit
    apparaître dans sa liste "Horaires à valider" → cliquer "Valider".
22. Créer un troisième compte, se connecter, et valider ce même horaire →
    le seuil par défaut (2) est atteint : le statut doit passer
    définitivement à "Validé", et l'horaire ne doit plus être modifiable
    par le membre qui l'a déclaré, même dans les 48h.
23. Avec le compte admin, aller sur "Admin" et ajouter un salaire brut
    mensuel pour le membre, avec une date d'effet dans le mois en cours.
    Retourner sur "Mon espace" du membre concerné (ou sa fiche via
    "Équipe" en tant qu'admin) : le taux horaire moyen du mois doit
    s'afficher (salaire ÷ heures validées ce mois-ci).
24. Se connecter avec le troisième compte (ni le membre concerné, ni
    admin) et consulter la fiche du membre via "Équipe" → le taux horaire
    ne doit pas être visible, seules les heures et le taux de présence.
25. Sur "Équipe", vérifier que le classement par heures travaillées et la
    mise en avant du membre en tête sont cohérents avec les horaires
    validés/déclarés saisis précédemment.
26. Avec le compte admin, désactiver le troisième compte → il ne doit plus
    pouvoir se reconnecter (message "compte désactivé"), et sa session en
    cours (si ouverte dans un autre onglet) doit être coupée dès la
    prochaine page visitée.

### Cartes pseudonymes — de bout en bout

27. Aller sur l'onglet "Cartes" → "Attribuer une nouvelle carte".
    Indiquer 2 adultes, ajouter 1 enfant avec la tranche "0-3", puis
    cliquer "Générer la carte". Un code au format `XXXX-XXXX-XXXX`
    s'affiche → le noter.
28. Retourner sur "Pointage". Cliquer "Scanner une carte", saisir le
    code noté à l'étape 27, et cliquer "Enregistrer le passage" → un
    message de confirmation s'affiche. Ouvrir `data/passages.xlsx` :
    la dernière ligne doit contenir `adultes=2, enfants=1,
    nouvelle_famille=Oui, mode=carte, carte=<le code>`.
29. Répéter l'étape 28 avec le même code → cette fois,
    `nouvelle_famille` doit être `Non` (ce n'est plus la première fois).
30. Cliquer "Passage sans carte", ajouter 1 adulte et 1 enfant,
    sélectionner "Oui" pour "Nouvelle famille aujourd'hui", valider →
    la nouvelle ligne dans le fichier Excel doit avoir
    `mode=anonyme, carte=` (vide).
31. Aller sur "Statistiques" → vérifier :
    - La section "Répartition par mode" affiche 2 passages carte et
      1 passage anonyme (plus les passages antérieurs éventuels).
    - La section "Familles distinctes (cartes)" affiche 1 famille carte.
    - La section "Tranches d'âge" affiche 1 enfant dans la tranche
      "0-3 ans".
32. Aller sur "Cartes" → "Modifier une fiche carte", saisir le code,
    ajouter un deuxième enfant (ex. date de naissance 2022-01-15),
    enregistrer → la fiche doit montrer 2 enfants. Un nouveau passage
    avec cette carte doit enregistrer `enfants=2`.
33. Saisir un code inexistant sur la page d'accueil (ex. `ABCD-EFGH-IJKL`)
    → un message d'erreur "Code inconnu" doit s'afficher, avec un lien
    vers l'attribution d'une nouvelle carte.

## Bilan CAF annuel (déclaration LAEP)

Un onglet "Bilan CAF" permet de préparer la déclaration annuelle auprès de
la CAF. Le bilan est organisé en trois volets conformes au formulaire CAF :

- **Volet 1 — Heures d'activité** : saisie des heures par accueillant,
  date et type d'activité (4 catégories CAF). Les heures d'organisation
  (préparation + analyse des pratiques + réunion d'équipe) et les heures
  de fonctionnement (ouverture au public + organisation) ne sont **jamais
  stockées** : elles sont calculées à l'affichage. Le nombre de séances
  correspond aux dates distinctes avec au moins une heure d'ouverture au
  public.
- **Volet 2 — Fréquentation annuelle** : dérivée automatiquement des
  passages enregistrés dans le module Pointage et des cartes pseudonymes.
  Aucune saisie supplémentaire n'est nécessaire. Les limites du comptage
  (familles anonymes, parents différents) sont les mêmes que celles
  documentées dans la section "Cartes pseudonymes" ci-dessus.
- **Volet 3 — Fiche d'identité de la structure** : caractéristiques
  annuelles du LAEP (local dédié, charte, supervision, partenariat,
  réseau, comité de pilotage) et observations complémentaires. Une seule
  fiche existe par année, modifiable à tout moment.

Les données du bilan sont dans `data/bilan.db` (SQLite, jamais versionnée),
distincte des autres bases (`heures.db`, `cartes.db`). Le volet comptable
et financier n'est pas couvert dans cette version.

### Comment saisir des heures d'activité

1. Aller sur "Bilan CAF" → "Accueillants" et ajouter les accueillants
   intervenant au LAEP (nom + rôle). Les accueillants désactivés ne sont
   plus proposés dans le formulaire de saisie mais leurs heures déjà
   enregistrées sont conservées.
2. Aller sur "Bilan CAF" → "Heures". Sélectionner l'accueillant, la date,
   le type d'activité parmi les 4 catégories CAF :
   - **Ouverture au public** : temps d'accueil effectif des familles
   - **Préparation, rangement, debriefing** : avant/après l'ouverture
   - **Analyse des pratiques / Supervision** : séances d'APP ou de
     supervision clinique
   - **Réunion d'équipe / Réseau** : réunions internes ou partenariales
3. Saisir la durée (heures + minutes) et cliquer "Enregistrer".
4. La navigation par mois et par année permet de consulter les heures
   enregistrées pour chaque période. Les heures peuvent être supprimées
   individuellement.

### Comment renseigner la fiche d'identité annuelle

1. Aller sur "Bilan CAF" → "Fiche structure".
2. Sélectionner l'année concernée.
3. Cocher les caractéristiques applicables à la structure (local dédié,
   charte signée, supervision, partenariat, réseau LAEP, comité de
   pilotage).
4. Renseigner les observations complémentaires si nécessaire.
5. Cliquer "Enregistrer la fiche". La fiche est modifiable à tout moment
   pour l'année en cours.

### Comment consulter le bilan annuel complet

1. Aller sur "Bilan CAF" → "Synthèse".
2. Sélectionner l'année avec le sélecteur en haut de page.
3. La page affiche les trois volets :
   - Le tableau mensuel des heures (les colonnes "Organisation" et
     "Fonctionnement" sont calculées automatiquement)
   - Les indicateurs de fréquentation (passages, adultes, enfants,
     familles, tranches d'âge)
   - La fiche d'identité de la structure
4. Le bouton "Imprimer" permet d'imprimer le bilan pour la déclaration
   CAF (les éléments de navigation sont masqués à l'impression).

### Bilan CAF — scénario de test de bout en bout

34. Aller sur l'onglet "Bilan CAF" → "Accueillants". Ajouter un
    accueillant (ex. "Marie Dupont", rôle "Accueillant") → confirmation,
    le nom apparaît dans la liste avec le statut "Actif".
35. Aller sur "Heures". Le dropdown accueillant doit proposer "Marie
    Dupont". Saisir une heure d'ouverture au public de 2h30 pour une
    date du mois en cours → confirmation "Heure enregistrée", la ligne
    apparaît dans le tableau avec "2h30".
36. Ajouter une deuxième heure de "Préparation, rangement, debriefing"
    de 1h pour la même date. Ajouter une troisième heure d'ouverture au
    public de 3h pour une date différente du même mois.
37. Aller sur "Synthèse" → vérifier :
    - Le tableau mensuel affiche les heures saisies sur le mois en cours
    - Total ouverture = 5h30, total préparation = 1h
    - La colonne "Organisation" affiche 1h (préparation seule)
    - La colonne "Fonctionnement" affiche 6h30 (5h30 + 1h)
    - Les cartes de synthèse indiquent 2 séances (2 dates d'ouverture
      distinctes)
    - Les mois sans données affichent "—" partout
38. Vérifier que le volet "Fréquentation annuelle" affiche les passages
    déjà enregistrés via le module Pointage (passages, adultes, enfants,
    familles distinctes par carte, nouvelles familles).
39. Aller sur "Fiche structure". Cocher "Local dédié", "Supervision" et
    "Réseau LAEP", ajouter une observation, puis enregistrer →
    confirmation "Fiche enregistrée". Recharger la page → les cases
    cochées et l'observation doivent être conservées.
40. Retourner sur "Synthèse" → le volet 3 affiche la fiche avec les
    réponses Oui/Non et les observations.
41. Changer l'année dans le sélecteur (ex. année précédente) → les trois
    volets doivent être vides (aucune heure, aucune fréquentation,
    aucune fiche). Revenir à l'année en cours → les données réapparaissent.
42. Sur "Accueillants", cliquer "Désactiver" sur Marie Dupont → le statut
    passe à "Inactif". Aller sur "Heures" → le dropdown accueillant ne
    doit plus proposer Marie Dupont, mais les heures déjà saisies sont
    toujours visibles. Réactiver le compte → Marie Dupont réapparaît dans
    le dropdown.
43. Vérifier qu'aucune page existante (Pointage, Statistiques, Cartes,
    Heures) n'est affectée par l'ajout du module Bilan CAF.
