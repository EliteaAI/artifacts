const ArtifactBucketUpdateModal = {
    components: {
        'input-stepper': InputStepper,
    },
    props: ['selectedBucket', 'minioQuery'],
    data() {
        return {
            bucketData: {
                name: '',
                retention: 'days',
                expiration: 1,
                storage: null,
            },
            isLoading: false,
        }
    },
    mounted() {
        const vm = this;
        $("#bucketUpdateModal").on("show.bs.modal", function (e) {
            vm.fetchBucket().then((bucket) => {
                vm.bucketData.name = vm.selectedBucket.name;
                vm.bucketData.retention = bucket.retention_policy.expiration_measure;
                vm.bucketData.expiration = bucket.retention_policy.expiration_value;
                $('#selectUpdatedRetention').val(vm.bucketData.retention)
                $('#selectUpdatedRetention').selectpicker('refresh');
            })
        });
        $('#selectUpdatedRetention').on('change', (e) => {
            this.bucketData.retention = e.target.value;
        })
    },
    methods: {
        setYear(val) {
            this.bucketData.expiration = val;
        },
        async fetchBucket() {
            // TODO rewrite session
            const api_url = this.$root.build_api_url('artifacts', 'artifacts')
            const res = await fetch (`${api_url}/${getSelectedProjectId()}/${this.selectedBucket.name}${this.minioQuery}`,{
                method: 'GET',
            })
            return res.json()
        },
        saveBucket() {
            this.isLoading = true
            const api_url = this.$root.build_api_url('artifacts', 'buckets')
            fetch(`${api_url}/${getSelectedProjectId()}${this.minioQuery}`,{
                method: 'PUT',
                headers: {'Content-Type': 'application/json', dataType: 'json'},
                body: JSON.stringify({
                    "name": this.bucketData.name,
                    "expiration_measure": (this.bucketData.retention).toLowerCase(),
                    "expiration_value": String(this.bucketData.expiration),
                })
            }).then((response) => response.json())
            .then(data => {
                this.isLoading = false;
                this.bucketData.name = '';
                $('#bucketUpdateModal').modal('hide');
                this.$emit('refresh-policy', { retention: this.bucketData.retention, expiration: this.bucketData.expiration});
                showNotify('SUCCESS', 'Bucket updated.');
            }).catch(err => {
                this.isLoading = false;
                showNotify('ERROR', err);
                console.log(err)
            })
        },
    },
    template: `
        <div class="modal modal-small fixed-left fade shadow-sm" tabindex="-1" role="dialog" id="bucketUpdateModal">
            <div class="modal-dialog modal-dialog-aside" role="document">
                <div class="modal-content">
                    <div class="modal-header">
                        <div class="row w-100">
                            <div class="col">
                                <h2>Update bucket</h2>
                            </div>
                            <div class="col-xs d-flex">
                                <button type="button" class="btn  btn-secondary mr-2" data-dismiss="modal" aria-label="Close">
                                    Cancel
                                </button>
                                <button type="button" 
                                    class="btn btn-basic d-flex align-items-center"
                                    @click="saveBucket"
                                >Save<i v-if="isLoading" class="preview-loader__white ml-2"></i></button>
                            </div>
                        </div>
                    </div>
                    <div class="modal-body">
                        <div class="section">
                            <div class="row">
                                <div class="custom-input mb-3 w-100">
                                    <label for="BucketName" class="font-weight-bold mb-1">Name</label>
                                    <input
                                        id="BucketName"
                                        type="text"
                                        v-model="bucketData.name"
                                        disabled
                                        placeholder="Bucket name">
                                </div>
                                <div class="row align-items-end mb-3">
                                    <div class="custom-input mr-2" id="retentionBlock">
                                        <label class="font-weight-bold mb-0">Retention policy</label>
                                        <p class="custom-input_desc mb-2">Description</p>
                                        <select class="selectpicker bootstrap-select__b" id="selectUpdatedRetention" data-style="btn">
                                            <option value="days">Days</option>
                                            <option value="years">Years</option>
                                            <option value="months">Months</option>
                                            <option value="weeks">Weeks</option>
                                        </select>
                                    </div>
                                    <div>
                                        <input-stepper 
                                            :default-value="bucketData.expiration"
                                            @change="setYear"
                                        ></input-stepper>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    `
}
