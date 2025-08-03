# warehouse/context_processors.py
from .models import SiteConfig

def site_config(request):
    cfg = SiteConfig.objects.first()
    return {
        'enable_qa_scan': cfg.enable_qa_scan if cfg else False
    }
