# Godmode

Godmode कोडिंग कार्य के दौरान निरंतरता और नियंत्रण के लिए एक local-first Codex
प्लगइन है। यह जाँचने-योग्य प्रमाणों से रिपॉज़िटरी की वास्तविकता का पुनर्निर्माण
करता है, परिचालन स्मृति को ट्रैक की गई फ़ाइलों से बाहर रखता है, और जोखिम भरी
कार्रवाइयों को घटित होने से पहले स्पष्ट करता है।

## गुण

- कोई telemetry, analytics, update ping, cloud sync, network listener, inference
  proxy, background daemon, या निष्क्रिय token उपयोग नहीं।
- निरंतरता भंडार में कोई कच्चा prompt, वार्तालाप, tool-output, environment,
  credential, या source-code संग्रह नहीं।
- Git रिपॉज़िटरी अपनी Git मेटाडेटा के नीचे स्थिति संग्रहीत करती हैं। गैर-Git
  प्रोजेक्ट ऑपरेटिंग-सिस्टम की application-data निर्देशिका के नीचे एक salted
  पहचानकर्ता उपयोग करते हैं।
- रिकॉर्ड schema-versioned, hash-chained, और atomic replacement से लिखे जाते हैं।
- संरक्षित संचालन को एक पूर्वावलोकन मिलता है और एक सीमित, समाप्त होने वाली,
  एक-बार-उपयोग स्थानीय क्षमता आवश्यक होती है। Godmode स्वयं कभी संचालन
  निष्पादित नहीं करता।
- संदर्भ रिपोर्टें देखे गए तथ्य, घोषित इरादे, धारणाएँ, बासी प्रमाण, विरोधाभास,
  और अनसुलझे दायित्वों में भेद करती हैं।
- Godmode पूर्ण स्मृति या सार्वभौमिक प्रवर्तन का वादा नहीं करता। यह हर दावे के
  पीछे का सटीक प्रमाण और adapter सीमा बताता है।

## शुरुआत

```powershell
python scripts/godmode.py --project . init
python scripts/godmode.py --project . inspect
python scripts/godmode.py --project . resume
```

कमांड सतह के लिए `python scripts/godmode.py --help` चलाएँ। बंडल की गई skills
एजेंट के कार्य को continuity, investigation, governance, या skill forging की
ओर भेजती हैं।

## निर्माण-से-निजी स्थिति

परिचालन योजनाएँ, checkpoints, handoffs, निर्णय, सबक़, घटनाएँ, sprint स्थिति,
और प्रमाण runtime रिकॉर्ड हैं। वे working tree में तब तक नहीं लिखे जाते जब तक
उपयोगकर्ता स्पष्ट रूप से एक sanitized रिपोर्ट निर्यात न करे।

Godmode को AIimagined विकसित करता है। यह पहचान केवल मेटाडेटा है और इसका कोई
runtime या user-interface व्यवहार नहीं है।
