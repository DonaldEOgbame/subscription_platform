import uuid
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils.text import slugify
from django.core.validators import MinValueValidator, MaxValueValidator


# -- Abstract Base Models --

class TimeStampedModel(models.Model):
    """Abstract model with created/updated timestamps."""
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class SoftDeleteModel(models.Model):
    """Abstract model for soft-deletion and active flag."""
    is_active  = models.BooleanField(default=True, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        abstract = True


# -- Core User & Organization Models --

class User(AbstractUser):
    """Custom user with role management and profile details."""
    class Roles(models.TextChoices):
        PROVIDER   = "provider",   "Service Provider"
        SUBSCRIBER = "subscriber", "Subscriber"
        ADMIN      = "admin",      "Platform Admin"

    role           = models.CharField(max_length=20, choices=Roles.choices, db_index=True)
    phone_number   = models.CharField(max_length=20, blank=True)
    profile_image  = models.ImageField(upload_to="profile_images/", null=True, blank=True)
    is_verified    = models.BooleanField(default=False)
    last_login_ip  = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['role']),
        ]


class Organization(TimeStampedModel, SoftDeleteModel):
    """Corporate or team account grouping multiple users."""
    name          = models.CharField(max_length=255)
    slug          = models.SlugField(unique=True, blank=True)
    description   = models.TextField(blank=True)
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=20, blank=True)
    members       = models.ManyToManyField(User, through="OrganizationMembership")

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    class Meta:
        indexes = [
            models.Index(fields=['slug']),
        ]

    def __str__(self):
        return self.name


class OrganizationMembership(TimeStampedModel):
    """Role of a user within an organization."""
    class OrgRoles(models.TextChoices):
        OWNER  = "owner",  "Owner"
        MEMBER = "member", "Member"

    user         = models.ForeignKey(User, on_delete=models.CASCADE)
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE)
    role         = models.CharField(max_length=10, choices=OrgRoles.choices)
    date_joined  = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "organization")
        indexes = [
            models.Index(fields=['organization', 'role']),
        ]

    def __str__(self):
        return f"{self.user.username} in {self.organization.name}"


# -- Global Platform Settings --

class PlatformSettings(TimeStampedModel):
    """Singleton for global billing, retry logic, templates, and taxes."""
    default_tax_rate        = models.DecimalField(
        max_digits=5, decimal_places=2, default=0,
        validators=[MinValueValidator(0)]
    )
    retry_attempts          = models.PositiveIntegerField(default=3)
    grace_period_days       = models.PositiveIntegerField(default=7)
    invoice_template        = models.TextField(blank=True)
    email_reminder_template = models.TextField(blank=True)

    class Meta:
        verbose_name = "Platform Settings"
        verbose_name_plural = "Platform Settings"


# -- Profile Models --

class ServiceProvider(TimeStampedModel, SoftDeleteModel):
    """Profile and metadata for service providers."""
    user                    = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="provider_profile"
    )
    company_name            = models.CharField(max_length=255, blank=True)
    description             = models.TextField(blank=True)
    rating                  = models.DecimalField(
        max_digits=3, decimal_places=2, default=0,
        validators=[MinValueValidator(0), MaxValueValidator(5)]
    )
    rating_count            = models.PositiveIntegerField(default=0)
    verification_status     = models.BooleanField(default=False)
    verification_documents  = models.JSONField(null=True, blank=True)
    website                 = models.URLField(blank=True)
    address                 = models.TextField(blank=True)
    social_links            = models.JSONField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['user', 'is_active']),
        ]

    def __str__(self):
        return f"Provider: {self.user.username}"


class Subscriber(TimeStampedModel, SoftDeleteModel):
    """Profile and metadata for subscribers."""
    user            = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="subscriber_profile"
    )
    loyalty_points  = models.PositiveIntegerField(default=0)
    date_of_birth   = models.DateField(null=True, blank=True)
    gender          = models.CharField(max_length=20, blank=True)
    address         = models.TextField(blank=True)
    phone_number    = models.CharField(max_length=20, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['user', 'is_active']),
        ]

    def __str__(self):
        return f"Subscriber: {self.user.username}"


# -- Subscription & Usage Models --

class ServicePlan(TimeStampedModel, SoftDeleteModel):
    """Recurring subscription plan offered by a provider."""
    provider                  = models.ForeignKey(
        ServiceProvider, on_delete=models.PROTECT, related_name="plans"
    )
    name                      = models.CharField(max_length=255)
    slug                      = models.SlugField(unique=True, blank=True)
    description               = models.TextField()
    price                     = models.DecimalField(max_digits=10, decimal_places=2)
    currency                  = models.CharField(max_length=10, default="NGN")
    billing_interval          = models.CharField(max_length=20)  # e.g. "monthly", "annual"
    duration                  = models.DurationField()
    trial_period_days         = models.PositiveIntegerField(default=0)
    featured                  = models.BooleanField(default=False)
    category                  = models.CharField(max_length=100, blank=True)
    max_seats                 = models.PositiveIntegerField(null=True, blank=True)
    min_subscription_duration = models.PositiveIntegerField(
        null=True, blank=True, help_text="Minimum months"
    )
    paystack_plan_id          = models.CharField(max_length=100, unique=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    class Meta:
        indexes = [
            models.Index(fields=['slug']),
            models.Index(fields=['provider', 'is_active']),
        ]

    def __str__(self):
        return self.name


class AvailabilitySlot(TimeStampedModel, SoftDeleteModel):
    """Time slots when a provider is available."""
    provider        = models.ForeignKey(
        ServiceProvider, on_delete=models.CASCADE, related_name="availability_slots"
    )
    start_time      = models.DateTimeField(db_index=True)
    end_time        = models.DateTimeField()
    capacity        = models.PositiveIntegerField(default=1)
    deliverables    = models.TextField(blank=True)
    recurrence_rule = models.CharField(max_length=255, blank=True)
    timezone        = models.CharField(max_length=50, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['provider', 'start_time']),
        ]

    def __str__(self):
        return f"{self.provider.user.username} [{self.start_time} – {self.end_time}]"


class Subscription(TimeStampedModel, SoftDeleteModel):
    """Tracks an active (or historical) subscription."""
    class Status(models.TextChoices):
        ACTIVE   = "active",   "Active"
        PAUSED   = "paused",   "Paused"
        CANCELED = "canceled", "Canceled"
        EXPIRED  = "expired",  "Expired"

    subscriber                = models.ForeignKey(
        Subscriber, on_delete=models.PROTECT, related_name="subscriptions"
    )
    plan                      = models.ForeignKey(
        ServicePlan, on_delete=models.PROTECT, related_name="subscriptions"
    )
    status                    = models.CharField(
        max_length=20, choices=Status.choices, default=Status.ACTIVE, db_index=True
    )
    start_date                = models.DateField(auto_now_add=True, db_index=True)
    current_period_start      = models.DateTimeField(null=True, blank=True)
    current_period_end        = models.DateTimeField(null=True, blank=True)
    end_date                  = models.DateField(null=True, blank=True)
    auto_renew                = models.BooleanField(default=True)
    paystack_subscription_id  = models.CharField(max_length=100, null=True, blank=True, unique=True)
    quantity                  = models.PositiveIntegerField(default=1)
    cancel_at_period_end      = models.BooleanField(default=False)
    canceled_at               = models.DateTimeField(null=True, blank=True)
    paused_at                 = models.DateTimeField(null=True, blank=True)
    resumed_at                = models.DateTimeField(null=True, blank=True)
    latest_invoice_id         = models.CharField(max_length=100, null=True, blank=True)
    metadata                  = models.JSONField(null=True, blank=True)

    class Meta:
        unique_together = ("subscriber", "plan")
        indexes = [
            models.Index(fields=['subscriber', 'status']),
            models.Index(fields=['plan', 'status']),
        ]

    def __str__(self):
        return f"{self.subscriber.user.username} → {self.plan.name}"


class UsageRecord(TimeStampedModel):
    """Daily usage tracking for subscriptions."""
    subscription  = models.ForeignKey(
        Subscription, on_delete=models.CASCADE, related_name="usage_records"
    )
    date          = models.DateField(auto_now_add=True, db_index=True)
    sessions_used = models.IntegerField(default=0)
    downloads     = models.IntegerField(default=0)
    api_calls     = models.IntegerField(default=0)
    metadata      = models.JSONField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['subscription', 'date']),
        ]


# -- Event & Ticketing Models --

class Event(TimeStampedModel, SoftDeleteModel):
    """One-off or recurring event offerings."""
    provider        = models.ForeignKey(
        ServiceProvider, on_delete=models.PROTECT, related_name="events"
    )
    name            = models.CharField(max_length=255)
    slug            = models.SlugField(unique=True, blank=True)
    description     = models.TextField()
    image           = models.ImageField(upload_to="event_images/", null=True, blank=True)
    location_name   = models.CharField(max_length=255, blank=True)
    address         = models.TextField(blank=True)
    city            = models.CharField(max_length=100, blank=True)
    state           = models.CharField(max_length=100, blank=True)
    country         = models.CharField(max_length=100, blank=True)
    latitude        = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude       = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    is_online       = models.BooleanField(default=False)
    online_url      = models.URLField(blank=True)
    start_time      = models.DateTimeField(db_index=True)
    end_time        = models.DateTimeField()
    is_recurring    = models.BooleanField(default=False)
    recurrence_rule = models.CharField(max_length=255, blank=True)
    capacity        = models.PositiveIntegerField()
    min_age         = models.PositiveIntegerField(null=True, blank=True)
    max_age         = models.PositiveIntegerField(null=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    class Meta:
        indexes = [
            models.Index(fields=['slug']),
            models.Index(fields=['provider', 'start_time']),
        ]

    def __str__(self):
        return self.name


class TicketTier(TimeStampedModel, SoftDeleteModel):
    """Tiered pricing for event tickets."""
    event             = models.ForeignKey(
        Event, on_delete=models.PROTECT, related_name="ticket_tiers"
    )
    name              = models.CharField(max_length=100)
    description       = models.TextField(blank=True)
    price             = models.DecimalField(max_digits=10, decimal_places=2)
    currency          = models.CharField(max_length=10, default="NGN")
    capacity          = models.PositiveIntegerField()
    sales_start       = models.DateTimeField(null=True, blank=True)
    sales_end         = models.DateTimeField(null=True, blank=True)
    is_refundable     = models.BooleanField(default=True)
    paystack_price_id = models.CharField(max_length=100, null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['event', 'name']),
            models.Index(fields=['sales_start', 'sales_end']),
        ]

    def __str__(self):
        return f"{self.event.name} – {self.name}"


class Ticket(TimeStampedModel, SoftDeleteModel):
    """Digital ticket with QR code and check-in status."""
    class Status(models.TextChoices):
        ISSUED    = "issued",    "Issued"
        CHECKEDIN = "checkedin", "Checked In"
        CANCELED  = "canceled",  "Canceled"
        REFUNDED  = "refunded",  "Refunded"

    tier          = models.ForeignKey(
        TicketTier, on_delete=models.PROTECT, related_name="tickets"
    )
    subscriber    = models.ForeignKey(
        Subscriber, on_delete=models.PROTECT, related_name="tickets"
    )
    ticket_uuid   = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    qr_code       = models.CharField(max_length=255, unique=True)
    seat_number   = models.CharField(max_length=20, blank=True)
    status        = models.CharField(max_length=20, choices=Status.choices, default=Status.ISSUED, db_index=True)
    check_in_time = models.DateTimeField(null=True, blank=True)
    metadata      = models.JSONField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['ticket_uuid']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return str(self.ticket_uuid)


class WaitlistEntry(TimeStampedModel):
    """Waiting list for fully-booked events."""
    event      = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="waitlist")
    subscriber = models.ForeignKey(Subscriber, on_delete=models.CASCADE)
    position   = models.PositiveIntegerField()
    notified   = models.BooleanField(default=False)

    class Meta:
        unique_together = ("event", "subscriber")
        indexes = [
            models.Index(fields=['event', 'position']),
        ]

    def __str__(self):
        return f"{self.subscriber.user.username} on waitlist for {self.event.name}"


# -- Payment, Invoice & Webhook Models --

class PaymentTransaction(TimeStampedModel):
    """Record of all Paystack transactions and transfers."""
    class Types(models.TextChoices):
        CHARGE   = "charge",   "Charge"
        TRANSFER = "transfer", "Transfer"
        REFUND   = "refund",   "Refund"

    user                 = models.ForeignKey(User, on_delete=models.PROTECT)
    event                = models.ForeignKey(Event, on_delete=models.PROTECT, null=True, blank=True)
    subscription         = models.ForeignKey(Subscription, on_delete=models.PROTECT, null=True, blank=True)
    ticket               = models.ForeignKey(Ticket, on_delete=models.PROTECT, null=True, blank=True)
    amount               = models.DecimalField(max_digits=10, decimal_places=2)
    currency             = models.CharField(max_length=10, default="NGN")
    reference            = models.CharField(max_length=100, unique=True, db_index=True)
    status               = models.CharField(max_length=20, db_index=True)
    transaction_type     = models.CharField(max_length=20, choices=Types.choices)
    metadata             = models.JSONField(null=True, blank=True)
    ip_address           = models.GenericIPAddressField(null=True, blank=True)
    user_agent           = models.CharField(max_length=255, blank=True)
    raw_response         = models.JSONField(null=True, blank=True)

    def __str__(self):
        return self.reference


class Invoice(TimeStampedModel):
    """Invoices generated for payments or renewals."""
    class Status(models.TextChoices):
        DRAFT     = "draft",     "Draft"
        SENT      = "sent",      "Sent"
        PAID      = "paid",      "Paid"
        OVERDUE   = "overdue",   "Overdue"
        CANCELED  = "canceled",  "Canceled"

    invoice_number = models.CharField(max_length=100, unique=True, db_index=True)
    user           = models.ForeignKey(User, on_delete=models.PROTECT)
    subscription   = models.ForeignKey(Subscription, on_delete=models.SET_NULL, null=True, blank=True)
    payment        = models.OneToOneField(PaymentTransaction, on_delete=models.SET_NULL, null=True, blank=True)
    issue_date     = models.DateField(auto_now_add=True, db_index=True)
    due_date       = models.DateField(null=True, blank=True)
    status         = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True)
    subtotal       = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    tax_amount     = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    total_amount   = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    pdf            = models.FileField(upload_to="invoices/", blank=True)
    metadata       = models.JSONField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['invoice_number']),
            models.Index(fields=['status', 'issue_date']),
        ]

    def __str__(self):
        return self.invoice_number


class PaystackWebhook(TimeStampedModel):
    """Logs raw Paystack webhook events and processing status."""
    class Status(models.TextChoices):
        PENDING   = "pending",   "Pending"
        PROCESSED = "processed", "Processed"
        FAILED    = "failed",    "Failed"

    event         = models.CharField(max_length=100)
    payload       = models.JSONField()
    status        = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    processed     = models.BooleanField(default=False)
    processed_at  = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['event', 'status']),
        ]

    def __str__(self):
        return f"{self.event} @ {self.created_at}"


# -- Promotion & Bundling Models --

class Coupon(TimeStampedModel, SoftDeleteModel):
    """Discount codes for plans or events."""
    class DiscountType(models.TextChoices):
        PERCENTAGE = "percentage", "Percentage"
        FIXED      = "fixed",      "Fixed"

    code                = models.CharField(max_length=50, unique=True, db_index=True)
    name                = models.CharField(max_length=255, blank=True)
    description         = models.TextField(blank=True)
    discount_type       = models.CharField(max_length=10, choices=DiscountType.choices)
    value               = models.DecimalField(max_digits=10, decimal_places=2)
    min_purchase_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    usage_limit         = models.PositiveIntegerField(null=True, blank=True)
    times_redeemed      = models.PositiveIntegerField(default=0)
    expires_at          = models.DateTimeField(null=True, blank=True, db_index=True)
    applicable_plans    = models.ManyToManyField(ServicePlan, blank=True)
    applicable_events   = models.ManyToManyField(Event, blank=True)
    metadata            = models.JSONField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['code']),
            models.Index(fields=['expires_at', 'is_active']),
        ]

    def __str__(self):
        return self.code


class Bundle(TimeStampedModel, SoftDeleteModel):
    """Bundle offers combining plans and events at a special price."""
    name            = models.CharField(max_length=255)
    slug            = models.SlugField(unique=True, blank=True)
    description     = models.TextField(blank=True)
    plans           = models.ManyToManyField(ServicePlan, blank=True)
    events          = models.ManyToManyField(Event, blank=True)
    price           = models.DecimalField(max_digits=10, decimal_places=2)
    currency        = models.CharField(max_length=10, default="NGN")
    max_redemptions = models.PositiveIntegerField(null=True, blank=True)
    times_redeemed  = models.PositiveIntegerField(default=0)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    class Meta:
        indexes = [
            models.Index(fields=['slug']),
        ]

    def __str__(self):
        return self.name


# -- Loyalty & Referral Models --

class LoyaltyTransaction(TimeStampedModel):
    """History of loyalty point changes."""
    class Types(models.TextChoices):
        EARN   = "earn",   "Earn"
        REDEEM = "redeem", "Redeem"

    subscriber = models.ForeignKey(
        Subscriber, on_delete=models.CASCADE, related_name="loyalty_transactions"
    )
    points     = models.IntegerField()
    balance    = models.IntegerField()
    type       = models.CharField(max_length=10, choices=Types.choices)
    reason     = models.CharField(max_length=255, blank=True)
    reference  = models.CharField(max_length=100, blank=True)
    metadata   = models.JSONField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['subscriber', 'type']),
        ]

    def __str__(self):
        return f"{self.type.capitalize()} {self.points} pts"


class ReferralLink(TimeStampedModel, SoftDeleteModel):
    """Custom referral links for affiliate tracking."""
    code            = models.CharField(max_length=100, unique=True, db_index=True)
    url             = models.URLField()
    provider        = models.ForeignKey(
        ServiceProvider, on_delete=models.CASCADE, related_name="referral_links", null=True, blank=True
    )
    promoter        = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="promoted_links", null=True, blank=True
    )
    description     = models.TextField(blank=True)
    payout_rate     = models.DecimalField(
        max_digits=5, decimal_places=2, default=0, validators=[MinValueValidator(0)]
    )
    expiration_date = models.DateTimeField(null=True, blank=True, db_index=True)
    max_uses        = models.PositiveIntegerField(null=True, blank=True)
    used_count      = models.PositiveIntegerField(default=0)
    metadata        = models.JSONField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['code', 'expiration_date']),
        ]

    def __str__(self):
        return self.code


class AffiliateCommission(TimeStampedModel):
    """Commission earned through referral links."""
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PAID    = "paid",    "Paid"

    referral_link = models.ForeignKey(
        ReferralLink, on_delete=models.CASCADE, related_name="commissions"
    )
    transaction   = models.ForeignKey(
        PaymentTransaction, on_delete=models.CASCADE, related_name="commissions"
    )
    amount        = models.DecimalField(max_digits=10, decimal_places=2)
    status        = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    paid_at       = models.DateTimeField(null=True, blank=True)
    metadata      = models.JSONField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['referral_link', 'status']),
        ]

    def __str__(self):
        return f"Commission {self.amount}"


# -- Payout & Payment Distribution Models --

class Payout(TimeStampedModel):
    """Scheduled and processed payouts to providers."""
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PAID    = "paid",    "Paid"
        FAILED  = "failed",  "Failed"

    provider             = models.ForeignKey(
        ServiceProvider, on_delete=models.CASCADE, related_name="payouts"
    )
    amount               = models.DecimalField(max_digits=10, decimal_places=2)
    currency             = models.CharField(max_length=10, default="NGN")
    paystack_transfer_id = models.CharField(max_length=100, unique=True, db_index=True)
    scheduled_for        = models.DateTimeField(db_index=True)
    processed_at         = models.DateTimeField(null=True, blank=True, db_index=True)
    status               = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    attempts             = models.PositiveIntegerField(default=0)
    last_error           = models.TextField(blank=True)
    processed_by         = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="processed_payouts"
    )
    metadata             = models.JSONField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['provider', 'status']),
        ]

    def __str__(self):
        return f"Payout {self.id} to {self.provider.user.username}"


# -- Calendar Sync --

class CalendarSync(TimeStampedModel, SoftDeleteModel):
    """External calendar integration tokens."""
    class CalendarService(models.TextChoices):
        GOOGLE  = "google",  "Google Calendar"
        OUTLOOK = "outlook", "Outlook"

    provider      = models.ForeignKey(
        ServiceProvider, on_delete=models.CASCADE, related_name="calendar_syncs"
    )
    service       = models.CharField(max_length=50, choices=CalendarService.choices)
    token         = models.CharField(max_length=255)
    refresh_token = models.CharField(max_length=255, blank=True)
    expires_at    = models.DateTimeField(null=True, blank=True)
    synced_at     = models.DateTimeField(auto_now=True)
    metadata      = models.JSONField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['provider', 'service']),
        ]

    def __str__(self):
        return f"{self.provider.user.username} – {self.service}"


# -- Analytics Snapshots --

class DailyMetric(TimeStampedModel):
    """Daily financial and engagement metrics snapshot."""
    date               = models.DateField(unique=True, db_index=True)
    total_mrr          = models.DecimalField(max_digits=12, decimal_places=2)
    churn_count        = models.PositiveIntegerField()
    new_signups        = models.PositiveIntegerField()
    mrr_delta          = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    new_revenue        = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    churned_revenue    = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    active_subscribers = models.PositiveIntegerField(default=0)
    snapshot_data      = models.JSONField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=['date']),
        ]

    def __str__(self):
        return str(self.date)
