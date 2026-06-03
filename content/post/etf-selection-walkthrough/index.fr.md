---
title: "Comment je construis mon propre portefeuille d'ETF"
description: "Une présentation technique de ma construction d'un portefeuille d'ETF de long terme : partir d'ETF liquides avec un historique long, exclure certains noms avant le clustering, sélectionner des ETF faiblement corrélés avec des rendements hebdomadaires ancrés, puis utiliser Hierarchical Risk Parity pour fixer les poids."
date: 2026-02-17
image: images/hrp_tree_weights.png
categories: ["Recherche quantitative", "Trading", "Construction de portefeuille"]
---
# Comment je construis mon propre portefeuille d'ETF

Tout part d'un problème concret de construction de portefeuille. On prend un
ensemble d'historiques de rendements d'ETF et on veut en tirer un panier qui
ne soit pas juste une pile de quasi-doublons.

L'objectif est simple : construire un portefeuille d'ETF pour un compte
personnel ou un compte de trading, pensé pour être détenu sur le long terme,
pas pour être traité comme un système de rotation rapide.

À haut niveau, le pipeline ne contient que deux étapes :

1. D'abord, sélectionner un groupe d'ETF faiblement corrélés entre eux.
2. Ensuite, lancer une optimisation de portefeuille pour fixer les poids.

Le processus se découpe en plusieurs phases :

1. Partir d'un grand univers d'ETF liquides avec un historique de trading
   suffisamment long.
2. Construire des paniers diversifiés à partir de la structure de corrélation.
3. Calculer les poids du portefeuille pour un panier donné.

Cette séparation compte parce qu'elle répond à deux questions différentes. La
couche de sélection demande quels ETF vont bien ensemble dans un panier
diversifié. La couche de pondération demande comment répartir le capital une
fois ce panier fixé.

## Partir de la partie de l'univers ETF que l'on traderait vraiment

Les détails opérationnels de l'accès à la base de données ne sont pas le sujet
ici, mais le filtre de départ compte vraiment. Je ne lance pas le clustering
par corrélation sur tout l'espace des ETF. Le processus réduit d'abord
l'univers à quelques centaines d'ETF avec un volume d'échange élevé et un
historique assez long pour être utilisables dans un portefeuille de long terme.

En pratique, cela commence par un filtre de liquidité sur l'univers ETF, puis
par un filtre sur la date de début avant d'exécuter les méthodes de
corrélation. Le point est pratique, pas académique : si un ETF est trop
illiquide ou trop récent pour inspirer confiance dans un compte personnel ou de
trading, il ne devrait même pas entrer dans la sélection.

Une fois cet univers fixé, le reste du pipeline s'appuie sur un seul jeu de
données quotidien partagé. Cette entrée commune compte parce qu'elle rend les
méthodes de sélection et de pondération comparables.

![Filtre de l'univers par liquidité et ancienneté](images/universe_filter.png)

Cette figure montre le premier écran de sélection. Le but n'est pas
d'explorer tout le menu des ETF. Le but est de partir de la portion de
l'univers ETF qui est assez liquide et assez ancienne pour être crédible dans
un portefeuille de long terme.

## Des prix quotidiens à une mesure de diversification

Soit $P_t$ le prix de clôture au jour de bourse $t$. Soit $r_t$ le rendement
logarithmique quotidien entre le jour $t-1$ et le jour $t$. Je calcule :

$$
r_t = \ln\left(\frac{P_t}{P_{t-1}}\right)
$$

Pour deux ETF $i$ et $j$, soit $\rho_{ij}$ la corrélation de rang de Spearman
de leurs séries de rendements. Je convertis ensuite cette corrélation en
distance :

$$
D_{ij} = \sqrt{0.5 \cdot \left(1 - \rho_{ij}\right)}
$$

Ce choix est au coeur de l'étape de sélection. Si deux ETF évoluent presque de
la même façon, alors $\rho_{ij}$ est proche de $1$ et la distance est proche
de $0$. S'ils évoluent en sens opposé, alors $\rho_{ij}$ baisse et la distance
augmente. C'est exactement ce que l'on veut pour une recherche de
diversification.

J'ai aussi testé ici plusieurs fréquences de rendement. La configuration prend
en charge des rendements quotidiens et hebdomadaires, et j'ai traité ce
compromis explicitement pendant le travail sur la sélection. Pour une
sélection d'ETF de long terme, je n'ai pas utilisé de données intrajournalières
même si le pipeline de données plus large y a accès. L'intrajournalier est trop
bruité pour cet horizon, et la logique de feature engineering de type "as-of"
relève d'un autre problème de recherche. Pour cette raison, la configuration de
sélection active est `RETURN_FREQUENCY = "weekly"`.

## La sélection est ancrée, pas libre

Une décision de conception compte plus qu'elle n'en a l'air au premier abord :
la sélection des ETF est ancrée sur `VOO` et `VEA`.

Ce choix d'ancrage n'a pas été présenté au code comme une vérité objective.
C'était un jugement subjectif. J'ai choisi de garder une ancre actions
américaines et une ancre actions développées hors États-Unis, puis de demander
aux méthodes de sélection de diversifier autour de ces deux noms.

Cela veut dire que l'on ne cherche pas ici un panier totalement libre à partir
de zéro. On part d'une ancre actions américaines imposée et d'une ancre actions
développées hors États-Unis imposée, puis on remplit les places restantes avec
des ETF qui ajoutent de la distance à cette base. Autrement dit, la question
n'est pas : "Quels sont les dix ETF les plus diversifiés du jeu de données ?" La
question est : "Compte tenu de ce coeur actions, qu'est-ce qui le diversifie
vraiment ?"

Dans le sélecteur glouton, cette contrainte est explicite :

```python
anchors = anchor_tickers if anchor_tickers is not None else utils.get_anchor_tickers()
anchor_tickers_resolved = utils.ensure_anchor_tickers(
    symbols, "greedy maximin survivors", anchors
)
seed_tickers = anchor_tickers_resolved[:n_select]
selected_idx = [sym_to_idx[ticker] for ticker in seed_tickers]
selected_tickers = seed_tickers.copy()
```

Cette conception ancre-d'abord rend les paniers sélectionnés plus faciles à
interpréter. Elle rend aussi les méthodes plus pratiques dans un vrai processus
de portefeuille, parce qu'elle ne prétend pas qu'un panier d'ETF diversifié
doit ignorer les expositions coeur qu'un investisseur s'attend déjà à garder.

Il y a aussi une autre couche subjective : la gestion d'une blacklist. La
configuration de sélection active n'accepte pas simplement tous les ETF
statistiquement éligibles. Elle exclut manuellement une liste significative de
noms, notamment `GLD`, `ASHR`, `ELV`, `KSA`, `EWZ`, `UGL`, `VNM`, `ECH`, `BAR`,
`SGOL`, `PHYS`, `OUNZ` et `GDXJ`. Ce n'est pas une étape purement algorithmique.
C'est un jugement explicite selon lequel certains ETF ne doivent pas concourir
pour le panier final, même s'ils passent les filtres de base sur les
rendements et la volatilité.

Cette blacklist doit agir avant le clustering et la sélection. Si je ne bloque
pas ces tickers dès la première étape, ils réapparaissent sans cesse dans les
clusters de corrélation et dans les listes finales de candidats. Le problème
n'est pas que les méthodes échouent mathématiquement. Le problème est qu'elles
continuent à faire remonter des ETF dans lesquels je ne veux pas engager de
capital. Le bon endroit pour les exclure est donc avant que les méthodes de
sélection commencent à voter.

En pratique, cela rend le processus semi-systématique plutôt que complètement
automatique. Les méthodes produisent des candidats diversifiés, mais le
processus de recherche continue à appliquer un jugement humain sur l'ensemble
des ancres et sur la liste des tickers qui doivent rester dehors.

## Comment le sélecteur glouton ajoute réellement des noms

L'une des quatre méthodes de sélection est le greedy maximin. Soit $S$
l'ensemble actuellement sélectionné. Pour chaque candidat restant $c$, la
méthode regarde la distance minimale entre $c$ et les noms déjà présents dans
$S$. Elle ajoute ensuite le candidat dont cette distance minimale est la plus
grande :

$$
c^* = \arg\max_{c \notin S} \min_{s \in S} D(c, s)
$$

Une fois les ancres fixées, l'implémentation conserve un vecteur courant des
distances minimales. Chaque étape n'a donc besoin que d'une seule mise à jour
contre l'ETF nouvellement ajouté :

```python
min_dist_masked = min_dist.copy()
min_dist_masked[selected_idx] = -np.inf
best_val = min_dist_masked.max()
tied_indices = np.where(np.abs(min_dist_masked - best_val) < 1e-12)[0].tolist()
next_idx = max(tied_indices, key=lambda i: vol_map.get(symbols[i], 0.0))
min_dist = np.minimum(min_dist, D[:, next_idx])
```

Cet exemple montre bien pourquoi la méthode est utile en recherche. L'idée est
mathématiquement propre, mais l'implémentation gère aussi les détails qui
comptent en pratique : des ancres fixes, un départage par la liquidité et une
courbe de diversité marginale enregistrée qui montre à quel moment les noms
supplémentaires n'apportent plus grand-chose.

## Ce que fait vraiment l'étape de corrélation

L'étape de corrélation n'essaie pas de maximiser le ratio de Sharpe ni de
prévoir le rendement total. Elle essaie de répondre à une question structurelle
plus étroite : quels ETF continuent d'apparaître comme des expositions
distinctes une fois que j'ai appliqué les contraintes pratiques qui comptent
pour moi ?

La vue `merged` reste utile sur le plan conceptuel, même sans graphique. Le
fichier sauvegardé `selected_merged.csv` indique si chaque ETF a été choisi
par Ward, greedy, k-medoids et max-div, puis compte combien de méthodes l'ont
retenu via la colonne `method_count`. Cela donne un résumé simple des noms qui
continuent de survivre à travers plusieurs sélecteurs fondés sur la
corrélation.

Cela compte pour la discussion sur la blacklist. Les décisions finales pour
garder ou écarter un ETF ne sont pas pilotées par un seul algorithme. Le
processus combine un jugement subjectif sur les ancres et les noms blacklistés
avec une vue par vote multi-méthodes de ce qui survit de manière répétée. Dit
autrement, la liste restreinte finale en pratique est façonnée à la fois par
l'intervention humaine et par l'accord de plusieurs méthodes de sélection.

C'est aussi pour cela que je ne veux pas faire reposer cette section sur le
ratio de Sharpe et des métriques similaires. À ce stade, un ETF à haut
rendement peut encore être un mauvais candidat s'il continue à encombrer le
même cluster, et un ETF faiblement corrélé peut encore être un mauvais
candidat si je n'ai tout simplement pas envie de le détenir.

![Carte de chaleur de corrélation hebdomadaire du panier retenu](images/low_correlation_heatmap.png)

Cette carte de chaleur est l'image que je veux montrer pour l'étape de faible
corrélation. Elle affiche directement la structure de corrélation de Spearman
hebdomadaire du panier retenu. Le but n'est pas de trouver des actifs qui ont
l'air différents par leur étiquette. Le but est de trouver des actifs qui ne
continuent pas à bouger ensemble une fois réduits à leurs rendements.

## Où HRP intervient dans la couche de pondération

La section de sélection ci-dessus parle volontairement de construction d'une
liste restreinte. Hierarchical Risk Parity, ou HRP, n'entre en jeu qu'une fois
cette liste restreinte déjà fixée. C'est la méthode de pondération que je veux montrer,
parce qu'elle correspond mieux à l'esprit de l'étape de sélection qu'un
optimiseur moyenne-variance pur.

HRP utilise la structure de clustering du panel de rendements pour répartir le
capital de manière récursive entre les branches de l'arbre de corrélation, au
lieu de s'appuyer sur l'inverse direct d'une matrice de covariance. Cela
compte parce que l'inversion de la covariance peut être fragile lorsque le
panier est petit et que les actifs restent fortement corrélés.

Cela rend HRP utile quand le panier est petit, corrélé et numériquement
délicat, ce qui est exactement l'environnement dans lequel vivent beaucoup de
paniers d'ETF. La méthode suit la séquence standard : construire une matrice de
corrélation de Spearman, la convertir en la même distance que celle utilisée
ailleurs, créer un arbre de Ward, puis allouer le capital par bisection
récursive.

```python
dist = np.sqrt(0.5 * (1.0 - corr))
condensed = squareform(dist, checks=False)
linkage_matrix = linkage(condensed, method="ward")
leaf_order = leaves_list(linkage_matrix).tolist()
```

HRP contient deux morceaux mathématiques utiles.

D'abord, à l'intérieur d'un cluster $C$, la méthode estime le risque du cluster
en formant un portefeuille à variance inverse sur ce cluster. Si $\Sigma_C$
est la matrice de covariance des actifs dans le cluster $C$, et si
$\sigma_i^2$ est la variance de l'actif $i$, alors les poids à variance inverse
à l'intérieur du cluster sont :

$$
w_i^{\mathrm{IVP}} = \frac{1 / \sigma_i^2}{\sum_{j \in C} 1 / \sigma_j^2}
$$

La variance du cluster est alors :

$$
\mathrm{Var}(C) = \left(w^{\mathrm{IVP}}\right)^\top \Sigma_C w^{\mathrm{IVP}}
$$

Ensuite, lorsqu'un cluster parent est séparé en une branche gauche $L$ et une
branche droite $R$, HRP alloue davantage de capital à la branche de plus faible
variance. Dans cette implémentation, l'allocation vers la branche gauche est :

$$
\alpha_L = 1 - \frac{\mathrm{Var}(L)}{\mathrm{Var}(L) + \mathrm{Var}(R)}
= \frac{\mathrm{Var}(R)}{\mathrm{Var}(L) + \mathrm{Var}(R)}
$$

et la branche droite reçoit $\alpha_R = 1 - \alpha_L$. Cette répartition est
ensuite appliquée récursivement jusqu'à ce que l'arbre atteigne des ETF
individuels.

```python
var_left, var_right = cluster_var(left), cluster_var(right)
total = var_left + var_right
alpha = (1.0 - var_left / total) if total > 0 else 0.5
```

La raison pratique d'utiliser HRP ici n'est pas qu'il garantit le rendement le
plus élevé. C'est qu'il garde l'étape de pondération alignée avec la même
logique de dépendance que celle utilisée dans la sélection. D'abord, l'ensemble
d'ETF est choisi selon la distance entre les actifs dans l'espace de
corrélation. Ensuite, on utilise une méthode de pondération qui respecte elle
aussi cette structure hiérarchique de co-mouvement.

![Arbre de clustering HRP et poids](images/hrp_tree_weights.png)

Cette figure est une meilleure visualisation de HRP qu'un simple histogramme
des poids, parce qu'elle montre les deux objets que la méthode utilise
vraiment. À gauche, l'arbre de clustering. À droite, le vecteur final de poids
HRP dans l'ordre du dendrogramme. Cela permet de voir plus facilement que HRP
ne se contente pas d'assigner des poids actif par actif. La méthode alloue le
capital branche par branche, puis propage ces décisions vers le bas de la
hiérarchie.

## Références

- Charles Spearman, “The Proof and Measurement of Association Between Two Things,” *The American Journal of Psychology*, 15(1), 72-101, 1904. [DOI](https://doi.org/10.2307/1412159)
- Joe H. Ward Jr., “Hierarchical Grouping to Optimize an Objective Function,” *Journal of the American Statistical Association*, 58(301), 236-244, 1963. [DOI](https://doi.org/10.1080/01621459.1963.10500845)
- Marcos López de Prado, “Building Diversified Portfolios that Outperform Out-of-Sample,” *The Journal of Portfolio Management*, 42(4), 59-69, 2016. [SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2708678)
- Yves Choueifaty and Yves Coignard, “Toward Maximum Diversification,” *The Journal of Portfolio Management*, 35(1), 40-51, 2008. [DOI](https://doi.org/10.3905/JPM.2008.35.1.40)
