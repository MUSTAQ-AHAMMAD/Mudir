<div dir="rtl" markdown="1">

# دليل النشر — مدير · Mudir / ORCHESTRA

> 🌐 ترجمة عربية لـ [`DEPLOYMENT.md`](../../DEPLOYMENT.md). عند الاختلاف يُعتمد الملف الإنجليزي.

توثيق نشر الإنتاج لحزمة مدير الذاتية الاستضافة (واجهة Node.js + لوحة React +
خدمات ORCHESTRA للذكاء الاصطناعي)، منسّقة عبر Docker Compose خلف وكيل عكسي nginx.

---

## 1. متطلبات النظام

| الملف التعريفي | المعالج | الذاكرة | القرص | GPU |
| --- | --- | --- | --- | --- |
| **GPU** (موصى به) | 8+ أنوية | 32 ج.ب+ | 100 ج.ب+ SSD | NVIDIA RTX 3060+ (12 ج.ب VRAM) |
| **CPU فقط** | 8+ أنوية | 32 ج.ب+ | 60 ج.ب+ SSD | — |

**البرمجيات:** Ubuntu 22.04 LTS، وDocker Engine مع Docker Compose v2، وGit، ولـ
GPU تعريفات NVIDIA + NVIDIA Container Toolkit.

افتح المنفذين **80** و**443** فقط للعامة. المنافذ الداخلية (3000، 5432، 8000،
9000، 11434) **لا تُنشَر** على المضيف — تُستخدَم فقط عبر شبكة compose الخاصة.

---

## 2. النشر خطوة بخطوة

```bash
# 1. استنساخ المستودع على الخادم
git clone https://github.com/MUSTAQ-AHAMMAD/Mudir.git /opt/mudir
cd /opt/mudir

# 2. ضبط البيئة
cp .env.production .env
nano .env   # POSTGRES_PASSWORD, بيانات WATI/Twilio + Supabase, PUBLIC_URL, OLLAMA_MODELS ...

# 3. وجّه سجلات DNS إلى الخادم ثم أصدر شهادات TLS (راجع nginx/ssl/README.md)

# 4. النشر (مضيف GPU)
./scripts/deploy.sh gpu
#    أو CPU فقط
./scripts/deploy.sh cpu

# 5. التحقق
./scripts/monitor.sh
```

المكافئ اليدوي:

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d   # GPU
docker compose -f docker-compose.yml -f docker-compose.cpu.yml up -d   # CPU
```

تفعيل المراقبة (اختياري):

```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml \
               -f docker-compose.monitoring.yml up -d
# Grafana → http://<المضيف>:3001 (admin / GRAFANA_ADMIN_PASSWORD)
```

---

## 3. العمليات التشغيلية

| المهمة | الأمر |
| --- | --- |
| لقطة صحّية | `./scripts/monitor.sh` |
| نسخ احتياطي لقاعدة البيانات + ChromaDB | `./scripts/backup.sh` |
| تحديث دون توقّف | `./scripts/update.sh gpu` |
| تجديد شهادات TLS | `./scripts/ssl-renew.sh` |
| عرض السجلّات | `docker compose logs -f backend` |
| توسيع الواجهة الخلفية | `docker compose up -d --scale backend=3` |

**النسخ الاحتياطي اليومي** عبر cron:

```cron
0 2 * * * cd /opt/mudir && ./scripts/backup.sh >> /var/log/mudir-backup.log 2>&1
```

خزّن نسخًا **خارج المضيف** ومشفّرة، واختبر الاستعادة بانتظام.

---

## 4. الأمان

- تبقى كل الأسرار في `.env` (مستثنى من git) أو في مدير أسرار — لا في الشيفرة.
- HTTPS فقط؛ إعادة توجيه HTTP إلى HTTPS مع تفعيل HSTS.
- تحديد المعدّل على `/webhook` و`/api` عند الحافة.
- التحقّق من توقيع ويب هوك واتساب.
- خدمات البيانات لا تُنشَر على المضيف — شبكة compose خاصة فقط.
- فعّل تشفير PostgreSQL أثناء السكون على مستوى المجلّد/المضيف (مثل LUKS).
- حافظ على تحديث المضيف والصور لسدّ الثغرات.

راجع [الأمان والخصوصية](../security.md) لمزيد من التفاصيل.

---

## 5. التوسّع

- **الواجهة الخلفية** عديمة الحالة — وسّعها أفقيًا (`--scale backend=N`)؛ يوازن
  nginx الحمل. انقل حالة تأكيد الرسائل الصوتية إلى **Redis** أولًا.
- **قاعدة البيانات** — أضف نسخًا للقراءة ووجّه الاستعلامات كثيفة القراءة إليها.
- **الأصول الثابتة** — ضع الواجهة الأمامية خلف CDN.
- **Kubernetes** — استخدم `k8s/deployment.yaml` مع Ingress وcert-manager.

راجع [الأداء والتوسّع](../performance.md) لإرشادات الحجم والقياس.

---

## 6. استكشاف الأخطاء

| العرض | التحقّق |
| --- | --- |
| خدمة عالقة `unhealthy` | `docker compose ps` ثم `docker compose logs <svc>` |
| GPU غير مستخدَم | تأكّد من NVIDIA Container Toolkit واستخدم ملف `gpu` |
| أول رد من Ollama بطيء | النموذج ما زال يُحمَّل — راقب `logs ollama` |
| خطأ 502 من nginx | الواجهة الخلفية ليست جاهزة بعد — تحقّق من `/health` |
| أخطاء TLS | الشهادات غير مُصدَرة/مجدَّدة — راجع `nginx/ssl/README.md` |
| رفض اتصال قاعدة البيانات | عدم تطابق `POSTGRES_PASSWORD`/`DATABASE_URL` في `.env` |

---

## 7. مرجع الإعدادات

راجع [`.env.production`](../../.env.production) للقائمة الكاملة المشروحة لمتغيّرات
البيئة (التشغيل، قاعدة البيانات، خدمات الذكاء الاصطناعي الذاتية، WATI/Twilio،
Supabase، قواعد العمل، تحديد المعدّل، الأعلام الميزاتية، المراقبة).

> لا تُودِع `.env` في git مطلقًا. استخدم مدير أسرار وبدّل بيانات الاعتماد دوريًا.

</div>
