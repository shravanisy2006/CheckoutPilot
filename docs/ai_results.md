### AI engine evaluation

**Rule checks** on 53 labelled synthetic scans (every combination of SDK version, PayPal placement and mobile layout, plus scanner edge cases):

| Issue | Precision | Recall | Correct detections | False alarms | Missed |
| --- | --- | --- | --- | --- | --- |
| `sdk_outdated` | 100% | 100% | 24 | 0 | 0 |
| `no_paypal_on_cart` | 100% | 100% | 24 | 0 | 0 |
| `no_paypal_on_product` | 100% | 100% | 24 | 0 | 0 |
| `button_below_fold_mobile` | 100% | 100% | 16 | 0 | 0 |

- Scans where every issue was exactly right: **53/53 (100%)**
- Same input gives the same ranking every run: **yes**
- High-severity issues always ranked first: **yes**
- Average time per scan (rules + ranking): **0.04 ms**

_Synthetic scans test the detection logic; they are not measurements on real stores._

**Vision model** on 8 hand-labelled screenshots:

| Issue | Precision | Recall | Correct | False alarms | Missed |
| --- | --- | --- | --- | --- | --- |
| `button_below_fold_mobile` | 100% | 100% | 1 | 0 | 0 |
| `no_paypal_on_cart` | 100% | 100% | 2 | 0 | 0 |

- Screenshots where every issue was exactly right: **8/8 (100%)**
- Average vision time per screenshot: **3.4 s**
