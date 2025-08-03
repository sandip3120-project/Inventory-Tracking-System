# warehouse/bartender.py

import requests
from django.conf import settings

def print_roll_label(roll):
    """
    Send a single‐record JSON job to BarTender’s REST API,
    containing only the QRData and Description fields.
    """
    url     = f"http://{settings.BT_HOST}:{settings.BT_PORT}/v1/print"
    qr_link = f"{settings.SITE_URL}/r/{roll.roll_id}"

    payload = {
      "LabelFormat": settings.BT_LABEL_TEMPLATE,
      "PrinterName": settings.BT_DEFAULT_PRINTER,
      "Records": [
        {
          # only the fields your .btw template binds to:
          "QRData":      qr_link,
          "Description": roll.batch.material.description,
        }
      ]
    }

    resp = requests.post(url, json=payload, timeout=5)
    resp.raise_for_status()
    return resp.json()
