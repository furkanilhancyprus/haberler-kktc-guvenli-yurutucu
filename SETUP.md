# Haberler KKTC güvenli medya yürütücüsü

Bu klasör, Vercel’e bağlı olmayan ayrı bir **özel GitHub deposunun** köküne konulacak test iş akışıdır. Canlı site ve Metricool takvimi ayrı kalır. `vercel-production-manifest.json`, mevcut Vercel üretim dağıtımının dosya kimliklerini kaydeder.

## Kurulum sırası

1. GitHub CLI erişimini yeniden yetkilendir. Özel depoyu oluşturup bu klasörü varsayılan dala yükle. GitHub harcama ayarında Actions için ücretsiz kota aşıldığında çalışmayı durduracak sınırı doğrula.
2. `MEDIA_API_TOKEN` değerini GitHub Actions repository secret olarak tanımla. Vercel’deki mevcut değer okunamıyorsa iki tarafa aynı yeni değeri güvenli biçimde yaz. Önce yürütücüyü hazırla, ardından Vercel üretim ortamına yeni değeri uygula ve aynı kaynak manifestiyle yeniden dağıt. Token’ı komut argümanı, prompt, log veya dosya içine koyma. GitHub CLI secret girişini standart girdiden alabilir.
3. GitHub Actions menüsünde **Haberler KKTC media runner → Run workflow** komutunu bir kez çalıştır. İş gerçek bir 1080×1350 JPEG gönderir. Aynı sabit anahtarı yeniden kullanır, URL’yi anonim indirir ve boyut, JPEG biçimi ve metadata’yı denetler. Çıktıda yalnızca HTTP sonucu, mediaId ve Blob URL’si yer alır.
4. HTTP 2xx ve doğrudan Blob görseli doğrulanırsa mevcut Metricool bağlantısıyla marka 7549135 üzerinde Facebook sağlayıcılı, `draft:true` ve `autoPublish:false` bir test taslağı oluştur. Önce aynı test için taslak bulunup bulunmadığını denetle. Taslağı yeniden okuyup görselin `static.metricool.com` adresine kopyalandığını doğrula. Bu testin Blob dosyasını yetkili araçla sil ve kopyayı yeniden aç. Önceki önizleme taslağını kullanma veya değiştirme.

## Saatlik plan

Cron ifadesi `30 * * * *`. GitHub zamanlanmış çalıştırmaları geciktirebilir. Saatlik iş varsayılan olarak kapalıdır. `MEDIA_RUNNER_HOURLY_CHECK` değişkeni `true` yapılırsa iş yalnızca yetkiyi Blob oluşturmadan kontrol eder. Zamanlanan kontrolde kimlik doğrulamadan sonra sunucunun boş gövdeye verdiği `413 INVALID_REQUEST_SIZE` beklenir. Elle başlatılan iş gerçek JPEG yükler.

Haber araştırması, görsel üretimi ve Metricool planlama bağlantısı bu iş akışına henüz eklenmedi. Bu aşamalar için otomasyonun çalıştığı ortamda üç kabiliyetin erişilebilirliği doğrulanmalı. Canlı Facebook yayını ve gerçek haberlerin otomatik Blob temizliği uçtan uca test ve ayrıca onay gerektiriyor.
