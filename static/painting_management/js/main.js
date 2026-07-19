// Painting Management - Shared Utilities
// Loaded on all painting management panel pages via painting_management/base.html

(function () {
    'use strict';

    window.PaintingApp = {
        confirm: function (message, callback) {
            if (confirm(message)) {
                callback();
            }
        },

        toast: function (message, type) {
            type = type || 'info';
            var toastId = 'toast-' + Date.now();
            var toastHtml = '<div id="' + toastId + '" class="toast align-items-center text-bg-' + type + ' border-0" role="alert">' +
                '<div class="d-flex"><div class="toast-body">' + message + '</div>' +
                '<button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button></div></div>';
            var $toast = $(toastHtml);
            $('body').append($toast);
            var bsToast = new bootstrap.Toast($toast[0]);
            bsToast.show();
            $toast.on('hidden.bs.toast', function () { $toast.remove(); });
        }
    };

})();
