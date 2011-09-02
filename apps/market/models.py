# -*- coding: utf-8 -*-
from django.db import models
from django.dispatch import receiver

from translations.fields import TranslatedField

from addons.models import Addon
import amo
import amo.models
from stats.models import Contribution
from users.models import UserProfile

import commonware.log
from jinja2.filters import do_dictsort


log = commonware.log.getLogger('z.market')


class PriceManager(amo.models.ManagerBase):

    def active(self):
        return self.filter(active=True)


class Price(amo.models.ModelBase):
    active = models.BooleanField(default=True)
    name = TranslatedField()
    price = models.DecimalField(max_digits=5, decimal_places=2)

    objects = PriceManager()
    currency = 'US'

    class Meta:
        db_table = 'prices'

    def __unicode__(self):
        return u'%s: %s' % (self.name, self.price)


class PriceCurrency(amo.models.ModelBase):
    currency = models.CharField(max_length=10,
                                choices=do_dictsort(amo.OTHER_CURRENCIES))
    price = models.DecimalField(max_digits=5, decimal_places=2)
    tier = models.ForeignKey(Price)

    class Meta:
        db_table = 'price_currency'
        verbose_name = 'Price currencies'

    def __unicode__(self):
        return u'%s, %s: %s' % (self.tier.name, self.currency, self.price)


class AddonPurchase(amo.models.ModelBase):
    addon = models.ForeignKey(Addon)
    user = models.ForeignKey(UserProfile)

    class Meta:
        db_table = 'addon_purchase'

    def __unicode__(self):
        return u'%s: %s' % (self.addon, self.user)


@receiver(models.signals.post_save, sender=Contribution,
          dispatch_uid='create_addon_purchase')
def create_addon_purchase(sender, instance, **kw):
    """
    When the contribution table is updated with the data from PayPal,
    update the addon purchase table. Will figure out if we need to add to or
    delete from the AddonPurchase table.
    """
    if (kw.get('raw') or
        instance.type not in [amo.CONTRIB_PURCHASE, amo.CONTRIB_REFUND,
                              amo.CONTRIB_CHARGEBACK]):
        # Whitelist the types we care about. Forget about the rest.
        return

    log.debug('Processing addon purchase type: %s, addon %s, user %s'
              % (amo.CONTRIB_TYPES[instance.type], instance.addon.pk,
                 instance.user.pk))

    if instance.type == amo.CONTRIB_PURCHASE:
        log.debug('Creating addon purchase: addon %s, user %s'
                  % (instance.addon.pk, instance.user.pk))
        AddonPurchase.objects.create(addon=instance.addon, user=instance.user)

    elif instance.type in [amo.CONTRIB_REFUND, amo.CONTRIB_CHARGEBACK]:
        purchases = AddonPurchase.objects.filter(addon=instance.addon,
                                                 user=instance.user)
        for p in purchases:
            log.debug('Deleting addon purchase: %s, addon %s, user %s'
                      % (p.pk, instance.addon.pk, instance.user.pk))
            p.delete()
