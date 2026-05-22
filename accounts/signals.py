from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender='accounts.User')
def sync_worker(sender, instance, created, **kwargs):
    from facilities.models import Worker

    if created:
        worker_no = f'W{instance.pk:05d}'
        Worker.objects.get_or_create(
            user=instance,
            defaults={
                'worker_no':   worker_no,
                'worker_name': instance.name or instance.username,
                'department':  instance.department,
                'phone':       instance.phone,
            },
        )
    else:
        try:
            worker = instance.worker
        except Worker.DoesNotExist:
            return

        fields = []
        new_name = instance.name or instance.username
        if worker.worker_name != new_name:
            worker.worker_name = new_name
            fields.append('worker_name')
        if worker.department_id != instance.department_id:
            worker.department = instance.department
            fields.append('department')
        if worker.phone != instance.phone:
            worker.phone = instance.phone
            fields.append('phone')
        if fields:
            fields.append('updated_at')
            worker.save(update_fields=fields)
