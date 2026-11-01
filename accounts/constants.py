BD_DISTRICTS = [
    # Dhaka division
    'Dhaka', 'Faridpur', 'Gazipur', 'Gopalganj', 'Kishoreganj', 'Madaripur', 'Manikganj',
    'Munshiganj', 'Narayanganj', 'Narsingdi', 'Rajbari', 'Shariatpur', 'Tangail',
    # Chattogram division
    'Bandarban', 'Brahmanbaria', 'Chandpur', 'Chattogram', "Cox's Bazar", 'Cumilla', 'Feni',
    'Khagrachhari', 'Lakshmipur', 'Noakhali', 'Rangamati',
    # Rajshahi division
    'Bogura', 'Chapainawabganj', 'Joypurhat', 'Naogaon', 'Natore', 'Pabna', 'Rajshahi',
    'Sirajganj',
    # Khulna division
    'Bagerhat', 'Chuadanga', 'Jashore', 'Jhenaidah', 'Khulna', 'Kushtia', 'Magura', 'Meherpur',
    'Narail', 'Satkhira',
    # Barishal division
    'Barguna', 'Barishal', 'Bhola', 'Jhalokati', 'Patuakhali', 'Pirojpur',
    # Sylhet division
    'Habiganj', 'Moulvibazar', 'Sunamganj', 'Sylhet',
    # Rangpur division
    'Dinajpur', 'Gaibandha', 'Kurigram', 'Lalmonirhat', 'Nilphamari', 'Panchagarh', 'Rangpur',
    'Thakurgaon',
    # Mymensingh division
    'Jamalpur', 'Mymensingh', 'Netrokona', 'Sherpur',
]

DISTRICT_CHOICES = [(d, d) for d in sorted(BD_DISTRICTS)]

INSIDE_DHAKA_DISTRICT = 'Dhaka'

BD_PHONE_REGEX = r'^(?:\+?88)?01[3-9]\d{8}$'
