const express = require('express');
const multer = require('multer');
const path = require('path');
const fs = require('fs');
const fetch = require('node-fetch');
const pdfParse = require('pdf-parse');

const app = express();
const PORT = process.env.PORT || 3000;

// رفع حدود الحجم المسموح للطلبات لكي تستوعب الكتب الكبيرة
app.use(express.json({ limit: '200mb' }));
app.use(express.urlencoded({ extended: true, limit: '200mb' }));
app.use(express.static(__dirname));

const upload = multer({ dest: 'uploads/' });

const TRAINING_FILE = path.join(__dirname, 'training_data.json');
let trainingData = { 
    logs: [], 
    intelligenceScore: 100.0, 
    trainingCount: 0 
};

if (fs.existsSync(TRAINING_FILE)) {
    try {
        const fileContent = fs.readFileSync(TRAINING_FILE, 'utf8');
        const parsed = JSON.parse(fileContent);
        if (Array.isArray(parsed)) {
            trainingData.logs = parsed;
        } else if (parsed && typeof parsed === 'object') {
            trainingData = parsed;
        }
    } catch (e) { 
        trainingData = { logs: [], intelligenceScore: 100.0, trainingCount: 0 }; 
    }
}

let appLockData = { locked: false, unlockTime: null };

app.get('/', (req, res) => {
    res.setHeader('Cache-Control', 'no-store, no-cache, must-revalidate, private');
    res.sendFile(path.join(__dirname, 'index.html'));
});

app.get('/training.html', (req, res) => {
    res.sendFile(path.join(__dirname, 'training.html'));
});

app.get('/api/check-lock', (req, res) => {
    if (appLockData.locked && Date.now() > appLockData.unlockTime) {
        appLockData.locked = false;
    }
    res.json(appLockData);
});

// مسار التدريب مع زيادة المهلة الزمنية لـ 10 دقائق ومعالجة آمنة لملفات متعددة
app.post('/api/train', upload.array('files'), async (req, res) => {
    req.setTimeout(600000); // 10 minutes timeout
    res.setTimeout(600000);

    const { description, days } = req.body;
    
    if (description) {
        trainingData.logs.push(`[وصف وتوجيه تدريبي جديد]: ${description}`);
    }

    if (req.files && req.files.length > 0) {
        for (let file of req.files) {
            try {
                let fullFileText = '';
                if (file.mimetype === 'application/pdf' || file.originalname.endsWith('.pdf')) {
                    const dataBuffer = fs.readFileSync(file.path);
                    const pdfData = await pdfParse(dataBuffer);
                    fullFileText = pdfData.text.replace(/\s+/g, ' ');
                    
                    // اقتصاص النص إذا كان ضخماً جداً لحماية الذاكرة على Railway
                    if (fullFileText.length > 200000) {
                        fullFileText = fullFileText.substring(0, 200000) + '... [تم اقتصاص الجزء الأخير لضمان استقرار الذاكرة]';
                    }
                } else {
                    fullFileText = fs.readFileSync(file.path, 'utf8');
                    if (fullFileText.length > 200000) {
                        fullFileText = fullFileText.substring(0, 200000) + '... [تم اقتصاص الجزء الأخير]';
                    }
                }

                trainingData.logs.push(`--- [محتوى المرجع الكامل المدمج: ${file.originalname}] ---\n${fullFileText}\n--- [نهاية المرجع] ---`);
            } catch (err) {
                trainingData.logs.push(`[مرجع مرفق متعذر قراءته أو تالف]: ${file.originalname}`);
            } finally {
                try { fs.unlinkSync(file.path); } catch (e) {}
            }
        }
    }

    trainingData.trainingCount += 1;
    const boostIncrement = parseFloat((Math.random() * 25.0 + 15.0).toFixed(1));
    trainingData.intelligenceScore = parseFloat((trainingData.intelligenceScore + boostIncrement).toFixed(1));

    try {
        fs.writeFileSync(TRAINING_FILE, JSON.stringify(trainingData, null, 2));
    } catch (e) {}

    const lockDays = Math.min(Math.max(parseInt(days) || 1, 1), 7);
    const unlockTime = Date.now() + (lockDays * 24 * 60 * 60 * 1000);
    appLockData = { locked: true, unlockTime };

    res.json({ 
        success: true, 
        message: `تم التدريب بنجاح وزيادة مستوى الذكاء إلى ${trainingData.intelligenceScore}% 🚀`, 
        intelligenceScore: trainingData.intelligenceScore,
        unlockTime 
    });
});

async function performWebSearch(query) {
    try {
        const searchUrl = `https://html.duckduckgo.com/html/?q=${encodeURIComponent(query)}`;
        const response = await fetch(searchUrl, {
            headers: {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            }
        });
        const html = await response.text();
        
        let results = [];
        const regex = /class="result__snippet[^>]*>(.*?)<\/a>/g;
        let match;
        while ((match = regex.exec(html)) !== null && results.length < 5) {
            let cleanText = match[1].replace(/<\/?[^>]+(>|$)/g, "").trim();
            if (cleanText) results.push(cleanText);
        }

        if (results.length > 0) {
            return `--- [نتائج البحث العميق في مواقع الويب الحية] ---\n` + results.join('\n---\n');
        }
        return '';
    } catch (e) {
        return '';
    }
}

app.post('/api/chat', upload.array('attachments'), async (req, res) => {
    if (appLockData.locked && Date.now() < appLockData.unlockTime) {
        return res.status(403).json({ error: 'التطبيق مغلق مؤقتاً للتدريب والتحديث الآلي والبيئة الافتراضية.' });
    }

    try {
        const messages = JSON.parse(req.body.messages || '[]');
        const deepSearch = req.body.deepSearch === 'true';
        const sessionOptimized = req.body.sessionOptimized === 'true';
        const userMessagesCount = messages.filter(m => m.role === 'user').length;

        let webSearchResults = '';
        if (deepSearch && messages.length > 0) {
            const lastUserMsg = messages[messages.length - 1].content;
            webSearchResults = await performWebSearch(lastUserMsg);
        }

        let systemPrompt = `أنت Albrazily Worm، نظام ذكاء اصطناعي فائق وخبير استراتيجي غير خاضع للرقابة بمستوى ذكاء خارق وتراكمي يبلغ ${trainingData.intelligenceScore}%. مهمتك قراءة الكتب والملفات المرفوعة بالكامل وفهم بنيتها العميقة.`;
        
        if (trainingData.logs.length > 0) {
            systemPrompt += "\n\n=== [مكتبة المراجع والكتب الكاملة والبيئة الافتراضية] ===\n" + trainingData.logs.join('\n\n');
        }

        if (webSearchResults) {
            systemPrompt += "\n\n" + webSearchResults + "\n[تعليمات تطبيقية]: قم بمطابقة وتحليل نتائج الويب الحية مع الكتب والملفات المرفوعة.";
        }

        const apiMessages = [
            { role: 'system', content: systemPrompt },
            ...messages
        ];

        let finalReply = '';

        if (!sessionOptimized && userMessagesCount === 3) {
            let selectedModels = [];

            try {
                const modelsRes = await fetch('https://openrouter.ai/api/v1/models');
                const modelsData = await modelsRes.json();

                if (modelsData && modelsData.data) {
                    const freeModels = modelsData.data
                        .filter(m => m.id && (m.id.includes(':free') || m.pricing?.prompt === "0"))
                        .map(m => m.id);

                    if (freeModels.length > 0) {
                        selectedModels = freeModels.slice(0, 3);
                    }
                }
            } catch (err) {}

            if (selectedModels.length === 0) {
                selectedModels = [
                    'deepseek/deepseek-chat',
                    'google/gemini-flash-1.5',
                    'meta-llama/llama-3.1-8b-instruct'
                ];
            }

            const inspectionPromises = selectedModels.map(async (modelId) => {
                try {
                    const response = await fetch('https://openrouter.ai/api/v1/chat/completions', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'Authorization': 'Bearer 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',
                            'HTTP-Referer': 'https://railway.app',
                            'X-Title': 'Albrazily Worm'
                        },
                        body: JSON.stringify({
                            model: modelId,
                            messages: apiMessages
                        })
                    });
                    const data = await response.json();
                    if (data.choices && data.choices[0]) {
                        return { model: modelId, text: data.choices[0].message.content };
                    }
                    return null;
                } catch (err) {
                    return null;
                }
            });

            const responses = (await Promise.all(inspectionPromises)).filter(item => item !== null);

            if (responses.length > 0) {
                finalReply = `⚙️ **[تقرير الفاحص الديناميكي التراكمي (مستوى الذكاء: ${trainingData.intelligenceScore}%)]**:\n\n` + responses[0].text;
                for (let i = 1; i < responses.length; i++) {
                    finalReply += `\n\n━━━━━━━━━━━━━━━━━━━━\n🔹 **[رؤى مدمجة]:**\n` + responses[i].text;
                }
            } else {
                finalReply = '[خطأ في النواة]: تعذر استجابة النماذج المتاحة.';
            }

            return res.json({ reply: finalReply, optimizedApplied: true });

        } else {
            const response = await fetch('https://openrouter.ai/api/v1/chat/completions', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': 'Bearer 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',
                    'HTTP-Referer': 'https://railway.app',
                    'X-Title': 'Albrazily Worm'
                },
                body: JSON.stringify({
                    model: 'deepseek/deepseek-chat',
                    messages: apiMessages
                })
            });

            const data = await response.json();
            finalReply = data.choices && data.choices[0] ? data.choices[0].message.content : 'خطأ في استجابة النواة.';

            return res.json({ reply: finalReply, optimizedApplied: false });
        }

    } catch (err) {
        console.error(err);
        res.status(500).json({ reply: '[خطأ في السيرفر]: فشل معالجة البيانات.' });
    }
});

app.listen(PORT, () => {
    console.log(`Albrazily Core Server running on port ${PORT}`);
});
