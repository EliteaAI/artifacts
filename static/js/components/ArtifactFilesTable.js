const ArtifactFilesTable = {
    props: ['selected-bucket', 'minioQuery'],
    data() {
        return {
            taskResults: {},
            url_prefix: window.url_prefix,
        }
    },
    methods: {
        uploadFiles(e) {
            const files = e.dataTransfer.files;
            Array.from(files).forEach(file => {
                this._uploadFile(file);
            });
        },
        _uploadFile(file) {
            const formData = new FormData()
            formData.append('file', file)
            const api_url = this.$root.build_api_url('artifacts', 'artifacts')
            $.ajax({
                url: `${api_url}/${getSelectedProjectId()}/${this.selectedBucket.name}${this.minioQuery}`,
                type: 'POST',
                data: formData,
                contentType: false,
                processData: false,
                success: (res) => {
                    this.$emit('refresh', res.size);
                    vueVm.registered_components.storage.getData();
                }
            });
        },
        deleteFiles() {
            const api_url = this.$root.build_api_url('artifacts', 'artifacts')
            let url = `${api_url}/${getSelectedProjectId()}/${this.selectedBucket.name}`
            this.minioQuery ? url += `${this.minioQuery}&` : url += `?`
            if ($("#artifact-table").bootstrapTable('getSelections').length > 0) {
                $("#artifact-table").bootstrapTable('getSelections').forEach(item => {
                    url += "fname[]=" + encodeURIComponent(item["name"]) + "&"
                });
                $.ajax({
                    url: url.substring(0, url.length - 1),
                    type: 'DELETE',
                    success: (res) => {
                        this.$emit('refresh', res.size);
                        vueVm.registered_components.storage.getData();
                    }
                });
            }
        },
        deleteFile(fileName, index) {
            const api_url = this.$root.build_api_url('artifacts', 'artifact')
            $.ajax({
                url: `${api_url}/${getSelectedProjectId()}/${this.selectedBucket.name}/${fileName}${this.minioQuery}`,
                type: 'DELETE',
                success: (res) => {
                    $('#artifact-table').bootstrapTable('remove', {
                        field: '$index',
                        values: [index]
                    })
                    this.$emit('refresh', res.size);
                    showNotify('SUCCESS', 'File delete.');
                }
            });
        },
        downloadFile(fileName, index) {
            const api_url = this.$root.build_api_url('artifacts', 'artifact')
            const url = `${api_url}/${getSelectedProjectId()}/${this.selectedBucket.name}/${encodeURIComponent(fileName)}${this.minioQuery}`
            $.ajax({
                url: url,
                method: 'GET',
                xhrFields: {
                    responseType: 'blob'
                },
                success: function (data) {
                    var a = document.createElement('a');
                    var url = window.URL.createObjectURL(data);
                    a.href = url;
                    a.download = fileName;
                    document.body.append(a);
                    a.click();
                    a.remove();
                    window.URL.revokeObjectURL(url);
                }
            });
        },
    },
    template: `
        <div class="card mt-3 mr-3 card-table-sm w-100" @dragover.prevent @drop.prevent>
            <div class="row pt-4 px-24">
                <div class="col-4">
                    <p class="font-h4 font-bold">Bucket {{ selectedBucket.name }}</p>
                    <p class="font-h6 font-weight-400">Retention policy - <span id="filesRetentionPolicy"></span></p>
                </div>
                <div class="col-8">
                    <div class="d-flex justify-content-end">
                        <button type="button"
                            @click="deleteFiles"
                            class="btn btn-secondary btn-icon btn-icon__purple">
                            <i class="icon__18x18 icon-delete"></i>
                        </button>
                    </div>
                </div>
            </div>
            <div class="card-body pt-4" @drop="uploadFiles">
                <table class="table table-borderless"
                    id="artifact-table"
                    data-toggle="table"
                    data-unique-id="id"
                    data-page-list="[5, 10, 15]"
                    data-pagination="true"
                    data-pagination-pre-text="<img src='${url_prefix}/design-system/static/assets/ico/arrow_left.svg'>"
                    data-pagination-next-text="<img src='${url_prefix}/design-system/static/assets/ico/arrow_right.svg'>"
                    data-page-size=5>
                    <thead class="thead-light">
                        <tr>
                            <th scope="col" data-checkbox="true"></th>
                            <th scope="col" data-sortable="true" data-field="name" class="w-100">NAME</th>
                            <th scope="col" data-sortable="true" data-cell-style="nameStyle" data-field="size" data-sorter="filesizeSorter">SIZE</th>
                            <th scope="col" data-sortable="true" data-cell-style="styleNoWrapText" data-field="modified"
                                data-formatter="filesFormatter.modified"
                            >LAST UPDATE</th>
                            <th scope="col" data-field="actions" data-align="right"
                                data-formatter="filesFormatter.actions"
                                data-events="filesFormatter.events"></th>
                        </tr>
                    </thead>
                    <tbody>
                    </tbody>
                </table>
            </div>
        </div>
    `
}

register_component('artifact-files-table', ArtifactFilesTable);
