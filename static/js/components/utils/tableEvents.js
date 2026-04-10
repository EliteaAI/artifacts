var bucketEvents = {
    "click .bucket_delete": function (e, value, row, index) {
        e.stopPropagation();
        const vm = vueVm.registered_components.artifact
        vm.openConfirm('single');
    },
    "click .bucket_setting": function (e, value, row, index) {
        e.stopPropagation();
        $('#bucketUpdateModal').modal('show');
    }
}

var filesFormatter = {
    actions(value, row, index) {
        return `
        <div class="d-flex justify-content-end">
            <div class="dropdown_multilevel">
                <button class="btn btn-default btn-xs btn-table btn-icon__xs" type="button"
                        data-toggle="dropdown" aria-haspopup="true" aria-expanded="false">
                    <i class="icon__18x18 icon-menu-dots"></i>
                </button>
                <ul class="dropdown-menu">
                    <li class="dropdown-menu_item dropdown-item d-flex align-items-center file_download">
                        <i class="icon__18x18 icon-download mr-2"></i><span class="w-100 font-h5">Download</span>
                    </li>
                    <li class="dropdown-menu_item dropdown-item d-flex align-items-center file_delete">
                        <i class="icon__18x18 icon-delete mr-2"></i><span class="w-100 font-h5">Delete</span>
                    </li>
                </ul>
            </div>
            
        </div>
    `
    },
    events: {
        "click .file_download": function (e, value, row, index) {
            vueVm.registered_components.artifactFiles.downloadFile(row.name, index);
        },
        "click .file_delete": function (e, value, row, index) {
            vueVm.registered_components.artifactFiles.deleteFile(row.name, index);
        },
    },
    modified(value) {
        return new Date(value).toLocaleString()
    }
}
