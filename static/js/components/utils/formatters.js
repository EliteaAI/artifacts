function filesizeSorter(a, b) {
    let a_number = retnum(a);
    let b_number = retnum(b);
    a = a_number;
    b = b_number;
    if (a > b) return 1;
    if (a < b) return -1;
    return 0;
}

function retnum(number) {
    let num = number.replace(/[^0-9]/g, '');
    const fileSizeName = number.replace(/[^a-zA-Z]+/g, '').toUpperCase();

    num = parseInt(num, 10);

    switch (fileSizeName) {
        case "K":
            num = num * 1024;
            break;
        case "M":
            num = num * Math.pow(1024, 2);
            break;
        case "G":
            num = num * Math.pow(1024, 3);
            break;
        case "T":
            num = num * Math.pow(1024, 4);
            break;
    }
    return num;
}