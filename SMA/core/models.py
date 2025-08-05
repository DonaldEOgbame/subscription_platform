from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Custom user with role management."""

    class Roles(models.TextChoices):
        PROVIDER = "provider", "Service Provider"
        SUBSCRIBER = "subscriber", "Subscriber"
        ADMIN = "admin", "Platform Admin"

    role = models.CharField(max_length=20, choices=Roles.choices)


class ServiceProvider(models.Model):
    """Additional data for service providers."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="provider_profile")
    description = models.TextField(blank=True)
    rating = models.DecimalField(max_digits=3, decimal_places=2, default=0)

    def __str__(self) -> str:
        return f"Provider: {self.user.username}"


class Subscriber(models.Model):
    """Profile for subscribers including loyalty points."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="subscriber_profile")
    loyalty_points = models.PositiveIntegerField(default=0)

    def __str__(self) -> str:
        return f"Subscriber: {self.user.username}"


class ServicePlan(models.Model):
    """Recurring subscription plan offered by a provider."""

    provider = models.ForeignKey(ServiceProvider, on_delete=models.CASCADE, related_name="plans")
    name = models.CharField(max_length=255)
    description = models.TextField()
    price = models.DecimalField(max_digits=10, decimal_places=2)
    billing_interval = models.CharField(max_length=20)
    duration = models.DurationField()
    category = models.CharField(max_length=100, blank=True)

    def __str__(self) -> str:
        return self.name


class AvailabilitySlot(models.Model):
    """Provider availability for sessions or events."""

    provider = models.ForeignKey(ServiceProvider, on_delete=models.CASCADE, related_name="availability_slots")
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    capacity = models.PositiveIntegerField(default=1)
    deliverables = models.TextField(blank=True)

    def __str__(self) -> str:
        return f"{self.provider.user.username} {self.start_time}"


class Subscription(models.Model):
    """Active subscription between a subscriber and a service plan."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        PAUSED = "paused", "Paused"
        CANCELED = "canceled", "Canceled"
        EXPIRED = "expired", "Expired"

    subscriber = models.ForeignKey(Subscriber, on_delete=models.CASCADE, related_name="subscriptions")
    plan = models.ForeignKey(ServicePlan, on_delete=models.CASCADE, related_name="subscriptions")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.ACTIVE)
    start_date = models.DateField(auto_now_add=True)
    end_date = models.DateField(null=True, blank=True)
    auto_renew = models.BooleanField(default=True)

    def __str__(self) -> str:
        return f"{self.subscriber.user.username} -> {self.plan.name}"


class UsageRecord(models.Model):
    """Tracks subscriber usage such as sessions or API calls."""

    subscription = models.ForeignKey(Subscription, on_delete=models.CASCADE, related_name="usage_records")
    date = models.DateField(auto_now_add=True)
    sessions_used = models.IntegerField(default=0)
    downloads = models.IntegerField(default=0)
    api_calls = models.IntegerField(default=0)


class Event(models.Model):
    """One-off or recurring events hosted by providers."""

    provider = models.ForeignKey(ServiceProvider, on_delete=models.CASCADE, related_name="events")
    name = models.CharField(max_length=255)
    description = models.TextField()
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    is_recurring = models.BooleanField(default=False)
    recurrence_rule = models.CharField(max_length=255, blank=True)
    capacity = models.PositiveIntegerField()

    def __str__(self) -> str:
        return self.name


class TicketTier(models.Model):
    """Different tiers for event tickets."""

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="ticket_tiers")
    name = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    capacity = models.PositiveIntegerField()
    seat_selection = models.BooleanField(default=False)

    def __str__(self) -> str:
        return f"{self.event.name} - {self.name}"


class Ticket(models.Model):
    """Digital ticket with QR code for check-in."""

    tier = models.ForeignKey(TicketTier, on_delete=models.CASCADE, related_name="tickets")
    subscriber = models.ForeignKey(Subscriber, on_delete=models.CASCADE, related_name="tickets")
    qr_code = models.CharField(max_length=255, unique=True)
    seat_number = models.CharField(max_length=20, blank=True)
    purchased_at = models.DateTimeField(auto_now_add=True)


class WaitlistEntry(models.Model):
    """Waiting list for full events."""

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="waitlist")
    subscriber = models.ForeignKey(Subscriber, on_delete=models.CASCADE)
    added_at = models.DateTimeField(auto_now_add=True)


class PaymentTransaction(models.Model):
    """Record of Paystack payments and transfers."""

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=10, default="NGN")
    reference = models.CharField(max_length=100, unique=True)
    status = models.CharField(max_length=20)
    created_at = models.DateTimeField(auto_now_add=True)
    provider_payout = models.BooleanField(default=False)


class Invoice(models.Model):
    """Invoices generated for payments or renewals."""

    user = models.ForeignKey(User, on_delete=models.CASCADE)
    subscription = models.ForeignKey(Subscription, on_delete=models.SET_NULL, null=True, blank=True)
    payment = models.OneToOneField(PaymentTransaction, on_delete=models.SET_NULL, null=True, blank=True)
    pdf = models.FileField(upload_to="invoices/", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class PaystackWebhook(models.Model):
    """Logs Paystack webhook events."""

    event = models.CharField(max_length=100)
    payload = models.JSONField()
    received_at = models.DateTimeField(auto_now_add=True)


class Coupon(models.Model):
    """Discount codes for plans or events."""

    class DiscountType(models.TextChoices):
        PERCENTAGE = "percentage", "Percentage"
        FIXED = "fixed", "Fixed"

    code = models.CharField(max_length=50, unique=True)
    discount_type = models.CharField(max_length=10, choices=DiscountType.choices)
    value = models.DecimalField(max_digits=10, decimal_places=2)
    usage_limit = models.PositiveIntegerField(null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)
    used_count = models.PositiveIntegerField(default=0)


class Bundle(models.Model):
    """Bundle offers combining plans and events."""

    name = models.CharField(max_length=255)
    plans = models.ManyToManyField(ServicePlan, related_name="bundles", blank=True)
    events = models.ManyToManyField(Event, related_name="bundles", blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)


class LoyaltyTransaction(models.Model):
    """History of loyalty points changes."""

    subscriber = models.ForeignKey(Subscriber, on_delete=models.CASCADE, related_name="loyalty_transactions")
    points = models.IntegerField()
    reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class ReferralLink(models.Model):
    """Referral link used for affiliate tracking."""

    provider = models.ForeignKey(ServiceProvider, on_delete=models.CASCADE, related_name="referral_links", null=True, blank=True)
    promoter = models.ForeignKey(User, on_delete=models.CASCADE, related_name="promoted_links", null=True, blank=True)
    code = models.CharField(max_length=100, unique=True)
    url = models.URLField()
    payout_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)


class AffiliateCommission(models.Model):
    """Commission earned through referrals."""

    referral_link = models.ForeignKey(ReferralLink, on_delete=models.CASCADE, related_name="commissions")
    transaction = models.ForeignKey(PaymentTransaction, on_delete=models.CASCADE, related_name="commissions")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    paid_out = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)


class CalendarSync(models.Model):
    """Stores tokens for external calendar integrations."""

    class CalendarService(models.TextChoices):
        GOOGLE = "google", "Google Calendar"
        OUTLOOK = "outlook", "Outlook"

    provider = models.ForeignKey(ServiceProvider, on_delete=models.CASCADE, related_name="calendar_syncs")
    service = models.CharField(max_length=50, choices=CalendarService.choices)
    token = models.CharField(max_length=255)
    synced_at = models.DateTimeField(auto_now=True)

