// main.js - توابع کمکی برای مدیریت نقاشی
// توجه: بیشتر تعاملات در قالب‌ها به صورت inline با jQuery پیاده‌سازی شده‌اند.
// این فایل شامل توابع عمومی قابل استفاده مجدد است.

// نمایش لیست کارگران با مهارت خاص در یک مودال
function showWorkerSelector(taskId, skill, csrfToken) {
    fetch('/painting/available-workers/?skill=' + encodeURIComponent(skill))
        .then(function (r) { return r.json(); })
        .then(function (data) {
            var body = document.querySelector('#assignModalBody');
            if (!body) return;
            if (!data.workers.length) {
                body.innerHTML = '<p class="text-muted">هیچ کارگری با این مهارت یافت نشد.</p>';
            } else {
                body.innerHTML = data.workers.map(function (w) {
                    return '<button class="btn btn-outline-primary m-1 select-worker" ' +
                        'data-task="' + taskId + '" data-worker="' + w.id + '">' +
                        w.name + ' (' + w.active_tasks + ' تسک فعال)</button>';
                }).join('');
            }
            var modal = document.getElementById('assignModal');
            if (modal && window.bootstrap) {
                new bootstrap.Modal(modal).show();
            }
        });
}

// تخصیص کارگر انتخاب‌شده به تسک
function assignWorkerToTask(taskId, workerId, csrfToken) {
    var fd = new FormData();
    fd.append('csrfmiddlewaretoken', csrfToken);
    fd.append('task_id', taskId);
    fd.append('worker_id', workerId);
    fetch('/painting/assign-worker/', {
        method: 'POST',
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
        body: fd
    })
    .then(function (r) { return r.json(); })
    .then(function (data) {
        if (data.success) { location.reload(); }
        else { alert('خطا: ' + (data.error || 'نامشخص')); }
    });
}
