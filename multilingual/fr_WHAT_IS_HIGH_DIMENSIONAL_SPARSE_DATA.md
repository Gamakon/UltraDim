# Pour les non-spécialistes : qu'est-ce que des données creuses de haute dimension ?

Je vais essayer d'expliquer à un public non technique comment il crée en permanence des données creuses de haute dimension, car c'est un concept important.

Bon, je suis sûr que vous avez déjà fait vos courses dans un grand supermarché, et je suppose que vous avez jeté un coup d'œil à votre ticket de caisse.

Ce sont des données creuses de haute dimension.

La question est : pourquoi ?

Chaque article sur les rayons du magasin porte un code-barres. C'est comme ça qu'on scanne vos courses quand vous payez, non ?

La caisse électronique et le scanner disposent d'une table de correspondance des codes-barres, et cette table détaille le code-barres numérique, la description du produit en langage humain, son prix de vente, et peut-être s'il est soumis à la taxe sur les ventes, ainsi que d'autres choses. Elle peut être assez volumineuse, puisqu'elle décrit tout ce que vend le magasin.

Maintenant, si j'avais toutes les données de tickets de caisse de Tous les clients, et que je voulais comparer votre comportement d'achat à celui des autres, je construirais la très très grande matrice suivante

(que vous pouvez vous représenter comme une très grande feuille de calcul) :

Nous avons une colonne pour chaque code-barres. Nous avons une ligne pour chaque client. Cela fera une Très Grande feuille de calcul ! Imaginez qu'il y ait quelque chose comme 300 000 codes-barres dans un grand Walmart, par exemple (les colonnes). Il pourrait y avoir 15 millions de clients (les lignes).

Maintenant, pour en revenir à votre ticket de caisse, imaginez que vous descendiez jusqu'à trouver votre identifiant client dans cette feuille de calcul, puis que vous parcouriez les colonnes en mettant un zéro si vous n'avez pas acheté ce produit, ou en inscrivant le nombre d'articles que vous avez achetés portant ce même code-barres.

Vous n'avez probablement pas acheté 300 000 choses lors de vos courses, il est donc assez évident que la plupart des cellules contiendraient un zéro pour vous, et c'est le cas pour tout le monde aussi. Si vous avez acheté 4 boîtes de soupe, cette colonne-là, pour votre ligne, contiendrait la valeur 4 dans la cellule, ce qui signifie que vous avez acheté 4 boîtes de cette soupe.

Nous utilisons le mot Creux pour décrire cette situation où la plupart des cellules sont à zéro pour tout le monde. Nous utilisons l'expression « de haute dimension » pour désigner le très grand nombre de colonnes (les produits).

Voilà comment vous créez en permanence des données creuses de haute dimension !

Notre base de données nous permet d'interroger ce jeu de données pour trouver la personne qui est votre plus proche voisin, c'est-à-dire la personne dont le panier de courses est, de manière mesurable, le plus semblable au vôtre. Nous le faisons en calculant l'angle cosinus entre votre vecteur d'achats et celui de chaque autre client. Nous pouvons le faire en quelques millisecondes, même s'il y a 40 millions de clients et 350 000 dimensions, grâce à des astuces mathématiques très complexes.

Cela signifie qu'UltraDim peut détecter des voisins quasi-identiques, recommander des produits utilisés par des Gens-Comme-Vous, identifier des anomalies (aucun voisin proche), construire des segmentations de clientèle pour personnaliser l'expérience client et faire un meilleur CRM, et même classifier les changements de comportement d'achat au fil du temps, à mesure, peut-être, que leur étape de vie change.

Et UltraDim fait cela sur les données natives, pas sur un résumé qui dégrade l'analyse.

Nous pouvons bien sûr indexer des jeux de données d'IA, c'est-à-dire des plongements de textes et de documents, et faire de la recherche augmentée par récupération, ce que signifie RAG. Mais les données de basse dimension, en dessous de 10 000 dimensions, peuvent être interrogées aujourd'hui avec des outils traditionnels. Notre vraie valeur se trouve dans ce nouveau territoire au-delà, où nos outils vous donnent la capacité de prendre de meilleures décisions stratégiques.

## Où trouve-t-on encore des données creuses de haute dimension ?

Ce type de jeu de données se rencontre PARTOUT, et on le résume dans des rapports qui en cachent la valeur.

Votre génome. Les données clients. Les données de cybersécurité. Les réseaux IoT. Les données de compteurs d'énergie. Les données de jumeaux numériques. Les données de transactions d'achat. Les données de chaîne d'approvisionnement. Les données boursières. Les jeux de données chimiques. Les jeux de données de physique. Les jeux de données de drones et de robots, y compris leurs capteurs embarqués. Les données de choix de films. Les données de recherche sémantique. Les données météorologiques. La liste est sans fin.

Nous imaginons un avenir, une frontière, où les ordinateurs et les humains collaborent, et notre mission chez Gamakon est de vous aider à *Naviguer la Frontière*.
