"""Word and sentence banks used to generate synthetic page text.

Main content and boilerplate are drawn from separate banks so that a leaked
boilerplate snippet can be told apart from real content by its n-grams.
"""

NEWS = {
    "subj": [
        "The city council", "Regional transport officials", "A coalition of local farmers",
        "The national weather service", "Hospital administrators", "University researchers",
        "The port authority", "Small business owners", "The state water board",
        "Teachers at the district's largest school",
    ],
    "verb": [
        "approved a plan to", "announced that they will", "voted on Tuesday to",
        "warned that delays could force them to", "began a formal review to",
        "are asking residents to help", "secured new funding to", "postponed a decision to",
    ],
    "obj": [
        "expand the northern rail line", "rebuild the flooded river walkway",
        "cut water use during the dry season", "open three new clinics",
        "replace aging school buses", "repair the coastal highway",
        "reopen the central library", "upgrade the harbor cranes",
        "plant twelve thousand street trees", "build a second runway",
    ],
    "tail": [
        "before the winter storms arrive", "after months of public hearings",
        "despite concerns about the budget", "with money from a federal grant",
        "according to a statement released on Monday", "while critics called the timeline unrealistic",
        "as ridership climbed for a third straight year", "once the environmental study is complete",
    ],
    "name": ["Maria Okafor", "Daniel Brooks", "Lena Fischer", "Tomas Herrera", "Priya Natarajan",
             "Hannah Cole", "Kenji Watanabe", "Amara Diallo"],
    "role": ["a retired engineer", "a bakery owner", "a nurse", "a bus driver", "a high school principal",
             "a ferry captain"],
    "detail": ["has lived near the river for forty years", "attended every hearing this spring",
               "commutes two hours each way", "organized the neighborhood petition"],
}

BLOG = {
    "subj": [
        "My first week of cycling to work", "Learning to bake sourdough", "Keeping a paper journal",
        "Moving to a smaller apartment", "Training for a half marathon", "Switching to a standing desk",
        "Growing tomatoes on a balcony", "Reading one book a week",
    ],
    "verb": [
        "taught me that", "reminded me that", "showed me quickly that", "convinced me that",
        "made it obvious that", "slowly proved that",
    ],
    "obj": [
        "small habits matter more than big plans", "the hardest part is starting",
        "rest days are part of the work", "cheap tools are often good enough",
        "writing things down clears my head", "most advice online is too complicated",
        "progress is rarely a straight line", "boredom is usually a sign to change routine",
    ],
    "tail": [
        "even on the rainy mornings", "and I wish I had started sooner",
        "although my neighbors still think I am strange", "which surprised me more than anything",
        "so I kept a simple log for thirty days", "and the numbers backed it up",
    ],
}

DOCS = {
    "subj": [
        "The worker pool", "Each queue", "The retry policy", "A scheduled job", "The result backend",
        "The command line tool", "A task handler", "The configuration loader",
    ],
    "verb": [
        "reads its settings from", "stores failed attempts in", "waits for confirmation from",
        "can be paused through", "sends progress events to", "falls back to",
    ],
    "obj": [
        "the environment file in the project root", "a local SQLite database",
        "the broker connection string", "the metrics endpoint", "the default timeout of thirty seconds",
        "the dead letter queue", "a JSON log stream",
    ],
    "tail": [
        "unless you override it explicitly", "when the process starts",
        "so you rarely need to configure it by hand", "which keeps restarts safe",
        "and this behavior is the same on every platform", "before any task is acknowledged",
    ],
}

PRODUCT = {
    "subj": [
        "The aluminum chassis", "The backlit keyboard", "The 14 inch display", "The battery",
        "The cooling system", "The trackpad", "The webcam", "The speaker array",
    ],
    "verb": [
        "is designed to", "lets you", "helps you", "was tuned to", "makes it easy to",
    ],
    "obj": [
        "stay cool during long video exports", "work a full day away from a charger",
        "type quietly in shared offices", "see accurate colors in bright rooms",
        "join calls with clear audio", "carry the laptop in a small bag",
    ],
    "tail": [
        "without adding weight", "even under heavy load", "on a single charge",
        "in almost any lighting", "while staying under 40 decibels",
    ],
}

FORUM = {
    "subj": [
        "My rear derailleur", "The chain on my road bike", "My new tubeless setup",
        "The front brake", "My bottom bracket", "The rear wheel hub",
    ],
    "verb": [
        "keeps slipping when I", "starts clicking whenever I", "loses pressure after I",
        "squeals loudly when I", "makes a grinding noise if I",
    ],
    "obj": [
        "shift into the smallest cog", "climb out of the saddle", "ride in the rain",
        "brake hard on descents", "leave it overnight", "pedal above 90 rpm",
    ],
    "tail": [
        "and I already replaced the cable", "even after a full cleaning",
        "but only on cold mornings", "so I am not sure what to check next",
        "and the shop could not reproduce it",
    ],
    "reply_open": [
        "Check the hanger alignment first.", "Sounds like cable tension to me.",
        "I had the same issue last spring.", "Try a different valve core before anything else.",
        "Have you measured chain stretch?",
    ],
    "user": ["gravel_gus", "spoke_and_mirror", "lanterne_rouge", "hill_repeats", "cassette_kate",
             "tubeless_tom", "crank_brother", "rando_rita"],
}

RECIPE = {
    "dish": ["Lemon herb roast chicken", "Smoky black bean soup", "Spinach and feta pie",
             "Weeknight vegetable curry", "Brown butter banana bread", "Garlic mushroom risotto"],
    "intro": [
        "This is the recipe I make when friends come over on short notice.",
        "It started as a way to use up leftovers and became a family favorite.",
        "The whole thing comes together in one pot with very little washing up.",
        "You can prepare most of it the night before and finish it in minutes.",
        "The trick is to cook the aromatics slowly so they turn sweet.",
    ],
    "ingredient": [
        "2 tablespoons olive oil", "1 large onion, finely chopped", "3 cloves garlic, minced",
        "1 teaspoon smoked paprika", "400 grams canned tomatoes", "1 cup vegetable stock",
        "200 grams fresh spinach", "1 lemon, zested and juiced", "salt and black pepper to taste",
        "2 ripe bananas, mashed", "100 grams unsalted butter", "250 grams arborio rice",
    ],
    "step": [
        "Heat the oil in a heavy pan over medium heat.", "Add the onion and cook for eight minutes until soft.",
        "Stir in the garlic and spices and cook for one more minute.",
        "Pour in the tomatoes and stock, then bring to a gentle simmer.",
        "Cover and cook for twenty minutes, stirring now and then.",
        "Fold in the spinach and lemon juice just before serving.",
        "Taste, adjust the seasoning and let it rest for five minutes.",
    ],
}

SITES = ["Harbor Daily", "Northwind Journal", "Copper Valley News", "The Morning Ledger", "Riverside Post",
         "Atlas Weekly"]

LISTING = {
    "category": ["Winter jackets", "Running shoes", "Wireless headphones", "Desk lamps", "Travel backpacks",
                 "Coffee grinders"],
    "brand": ["Northpeak", "Velo", "Aurora", "Kestrel", "Brightline", "Summit", "Harbor", "Lumen"],
    "adj": ["Classic", "Ultralight", "Pro", "Everyday", "Compact", "Insulated", "Trail", "Studio"],
}

# Non-English article sentences, written by hand. Each language has its own
# boilerplate lines so leaks can be detected the same way as in English pages.
NON_ENGLISH = {
    "es": {
        "title": "La ciudad aprueba un nuevo plan para el transporte publico",
        "sents": [
            "El ayuntamiento aprobo el martes un plan para ampliar la linea norte del tren.",
            "Los vecinos llevaban meses pidiendo mas frecuencias en las horas punta.",
            "Segun el informe tecnico, las obras empezaran antes del verano.",
            "La alcaldesa explico que el presupuesto incluye fondos europeos.",
            "Varios comerciantes temen que las obras reduzcan sus ventas durante meses.",
            "La oposicion considera que el calendario es demasiado optimista.",
            "El proyecto tambien preve nuevos carriles para bicicletas en el centro.",
            "Los primeros trenes nuevos llegaran a finales del proximo ano.",
        ],
        "nav": "Inicio Nacional Internacional Economia Cultura Deportes Opinion",
        "footer": "Todos los derechos reservados por el grupo editorial del diario regional",
        "cookie": "Utilizamos cookies propias y de terceros para mejorar su experiencia y mostrar publicidad personalizada segun sus habitos de navegacion",
        "related": "Otras noticias que le pueden interesar sobre la economia de la region",
    },
    "de": {
        "title": "Stadtrat beschliesst neuen Plan fuer den Nahverkehr",
        "sents": [
            "Der Stadtrat hat am Dienstag beschlossen, die noerdliche Bahnlinie zu verlaengern.",
            "Anwohner hatten seit Monaten mehr Verbindungen in der Hauptverkehrszeit gefordert.",
            "Laut dem technischen Bericht beginnen die Bauarbeiten noch vor dem Sommer.",
            "Die Buergermeisterin sagte, das Budget enthalte auch Mittel aus Bruessel.",
            "Einige Haendler befuerchten, dass die Baustelle ihre Umsaetze monatelang senkt.",
            "Die Opposition haelt den Zeitplan fuer viel zu optimistisch.",
            "Das Projekt sieht ausserdem neue Radwege in der Innenstadt vor.",
            "Die ersten neuen Zuege sollen Ende naechsten Jahres eintreffen.",
        ],
        "nav": "Startseite Politik Wirtschaft Kultur Sport Meinung Wissen",
        "footer": "Alle Rechte vorbehalten durch die regionale Verlagsgruppe und ihre Partner",
        "cookie": "Wir verwenden Cookies und aehnliche Technologien um Inhalte zu personalisieren und die Nutzung unserer Website zu analysieren",
        "related": "Weitere Artikel aus der Region die Sie interessieren koennten",
    },
    "fr": {
        "title": "La ville adopte un nouveau plan pour les transports",
        "sents": [
            "Le conseil municipal a vote mardi un plan pour prolonger la ligne nord du train.",
            "Les habitants reclamaient depuis des mois plus de trains aux heures de pointe.",
            "Selon le rapport technique, les travaux commenceront avant l'ete.",
            "La maire a precise que le budget comprend des fonds europeens.",
            "Plusieurs commercants craignent une baisse de leurs ventes pendant les travaux.",
            "L'opposition juge le calendrier beaucoup trop optimiste.",
            "Le projet prevoit aussi de nouvelles pistes cyclables dans le centre.",
            "Les premiers trains neufs arriveront a la fin de l'annee prochaine.",
        ],
        "nav": "Accueil Politique Economie Culture Sports Opinions Sciences",
        "footer": "Tous droits reserves par le groupe de presse regional et ses partenaires",
        "cookie": "Nous utilisons des cookies pour ameliorer votre experience et vous proposer des publicites adaptees a vos centres d'interet",
        "related": "A lire aussi les autres articles de la rubrique economie regionale",
    },
    "pt": {
        "title": "Prefeitura aprova novo plano para o transporte publico",
        "sents": [
            "A camara municipal aprovou na terca-feira um plano para ampliar a linha norte do trem.",
            "Os moradores pediam ha meses mais viagens nos horarios de pico.",
            "De acordo com o relatorio tecnico, as obras comecam antes do verao.",
            "A prefeita explicou que o orcamento inclui recursos federais.",
            "Alguns comerciantes temem que as obras reduzam as vendas por varios meses.",
            "A oposicao considera o cronograma otimista demais.",
            "O projeto tambem preve novas ciclovias no centro da cidade.",
            "Os primeiros trens novos devem chegar no final do proximo ano.",
        ],
        "nav": "Inicio Politica Economia Cultura Esportes Opiniao Ciencia",
        "footer": "Todos os direitos reservados ao grupo de comunicacao regional e seus parceiros",
        "cookie": "Usamos cookies para melhorar a sua experiencia e mostrar anuncios de acordo com os seus interesses de navegacao",
        "related": "Leia tambem outras noticias sobre a economia da regiao",
    },
    "it": {
        "title": "Il comune approva un nuovo piano per i trasporti",
        "sents": [
            "Il consiglio comunale ha approvato martedi un piano per estendere la linea nord del treno.",
            "I residenti chiedevano da mesi piu corse nelle ore di punta.",
            "Secondo la relazione tecnica, i lavori inizieranno prima dell'estate.",
            "La sindaca ha spiegato che il bilancio comprende fondi europei.",
            "Alcuni negozianti temono che il cantiere riduca le vendite per mesi.",
            "L'opposizione ritiene il calendario troppo ottimista.",
            "Il progetto prevede anche nuove piste ciclabili in centro.",
            "I primi treni nuovi arriveranno alla fine del prossimo anno.",
        ],
        "nav": "Home Politica Economia Cultura Sport Opinioni Scienza",
        "footer": "Tutti i diritti riservati dal gruppo editoriale regionale e dai suoi partner",
        "cookie": "Utilizziamo cookie tecnici e di profilazione per migliorare la tua esperienza e mostrarti pubblicita in linea con le tue preferenze",
        "related": "Leggi anche gli altri articoli sull'economia della regione",
    },
    "hi": {
        "title": "नगर निगम ने सार्वजनिक परिवहन की नई योजना को मंजूरी दी",
        "sents": [
            "नगर निगम ने मंगलवार को उत्तरी रेल लाइन बढ़ाने की योजना को मंजूरी दी।",
            "निवासी कई महीनों से व्यस्त समय में अधिक ट्रेनों की मांग कर रहे थे।",
            "तकनीकी रिपोर्ट के अनुसार निर्माण कार्य गर्मियों से पहले शुरू होगा।",
            "महापौर ने बताया कि बजट में केंद्र सरकार की सहायता भी शामिल है।",
            "कुछ दुकानदारों को डर है कि निर्माण से उनकी बिक्री महीनों तक घटेगी।",
            "विपक्ष का कहना है कि समय सीमा बहुत आशावादी है।",
            "योजना में शहर के बीच नई साइकिल लेन भी शामिल हैं।",
            "पहली नई ट्रेनें अगले साल के अंत तक पहुंचेंगी।",
        ],
        "nav": "होम देश दुनिया व्यापार मनोरंजन खेल राय",
        "footer": "सर्वाधिकार सुरक्षित क्षेत्रीय समाचार समूह और उसके सहयोगी",
        "cookie": "हम आपके अनुभव को बेहतर बनाने और आपकी रुचि के अनुसार विज्ञापन दिखाने के लिए कुकीज़ का उपयोग करते हैं",
        "related": "क्षेत्र की अर्थव्यवस्था से जुड़ी अन्य खबरें भी पढ़ें",
    },
}

# Boilerplate banks (kept lexically apart from main text).
COOKIE_LINES = [
    "We use cookies and similar technologies to personalise content, measure advertising and improve your experience on our site.",
    "By clicking Accept all you consent to the storage of cookies on your device to enhance site navigation and analyse usage.",
    "Our partners may combine this information with other data you have provided to them or that they have collected from your use of their services.",
]
MODAL_LINES = [
    "Get our free morning briefing delivered straight to your inbox every weekday before breakfast.",
    "Join more than two hundred thousand subscribers who start their day with our editors' picks and exclusive offers.",
    "You can unsubscribe at any time using the link at the bottom of every email we send you.",
]
SIDEBAR_BIO = [
    "About the author: she covered municipal politics for a decade before moving to the data desk, and she still answers every reader letter personally.",
    "About the author: he writes about cities, infrastructure and the people who keep them running, and lives with two loud cats.",
]
POPULAR = [
    "Ten weekend getaways you can reach without a car this autumn",
    "Why everyone suddenly wants a heat pump and what it really costs",
    "The quiet comeback of the neighborhood video rental shop",
    "How one baker turned a garage into the busiest cafe in town",
    "What the new parking rules mean for drivers who work night shifts",
    "Inside the volunteer crew that restores old pianos for schools",
]
COMMENT_LINES = [
    "Great post, thanks for sharing this, I have bookmarked it for later reading tonight.",
    "I tried this last year and gave up after a month, maybe I will give it another shot.",
    "Does anyone know whether this works for people living in very small flats with no balcony?",
    "This is exactly the kind of honest write up I was looking for, keep them coming please.",
    "Totally disagree with the third point, but the rest is spot on in my experience.",
    "Love the photos, which camera did you use for the sunset ones near the end?",
]
SIGNATURES = [
    "Sent from my phone, apologies for any typos in this message.",
    "Two wheels good, four wheels bad, see you all on the Sunday club ride.",
    "Currently riding a steel frame from 1987 and refusing to upgrade anything.",
]
